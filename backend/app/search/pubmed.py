from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from uuid import uuid4

import httpx

from app.core.config import Settings, get_settings
from app.schemas.chat import Paper, SearchFilters


class LiteratureSearchClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def search(
        self,
        query: str,
        max_results: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        if self.settings.demo_mode:
            return demo_papers(query, max_results)
        filters = filters or SearchFilters()
        europe_limit = max(3, max_results // 2)
        pubmed_limit = max(3, max_results - europe_limit)
        results = await asyncio.gather(
            self._search_europe_pmc(query, europe_limit, filters),
            self._search_pubmed(query, pubmed_limit, filters),
            return_exceptions=True,
        )
        papers: list[Paper] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            papers.extend(result)
        return _dedupe_papers(papers)[:max_results]

    async def _search_europe_pmc(
        self,
        query: str,
        max_results: int,
        filters: SearchFilters,
    ) -> list[Paper]:
        clauses = [query]
        if filters.year_from:
            year_to = filters.year_to or 3000
            clauses.append(f"FIRST_PDATE:[{filters.year_from}-01-01 TO {year_to}-12-31]")
        if filters.open_access_only:
            clauses.append("OPEN_ACCESS:y")
        if filters.study_type:
            type_clause = " OR ".join(f'PUB_TYPE:"{item}"' for item in filters.study_type)
            clauses.append(f"({type_clause})")

        params = {
            "query": " AND ".join(clauses),
            "format": "json",
            "pageSize": max_results,
            "resultType": "core",
            "sort": "P_PDATE_D desc",
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params=params,
            )
            response.raise_for_status()
        results = response.json().get("resultList", {}).get("result", [])
        return [_europe_pmc_to_paper(item) for item in results[:max_results]]

    async def _search_pubmed(
        self,
        query: str,
        max_results: int,
        filters: SearchFilters,
    ) -> list[Paper]:
        term = _pubmed_query(query, filters)
        params = {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": max_results,
            "sort": "pub date",
            "tool": self.settings.app_name,
        }
        if self.settings.ncbi_email:
            params["email"] = self.settings.ncbi_email
        if self.settings.ncbi_api_key:
            params["api_key"] = self.settings.ncbi_api_key

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            search_response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params=params,
            )
            search_response.raise_for_status()
            ids = search_response.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(ids[:max_results]),
                "retmode": "xml",
                "tool": self.settings.app_name,
            }
            if self.settings.ncbi_email:
                fetch_params["email"] = self.settings.ncbi_email
            if self.settings.ncbi_api_key:
                fetch_params["api_key"] = self.settings.ncbi_api_key
            fetch_response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params=fetch_params,
            )
            fetch_response.raise_for_status()
        return _pubmed_xml_to_papers(fetch_response.text)


def demo_papers(query: str, max_results: int = 10) -> list[Paper]:
    query_hint = " ".join(query.split())[:120]
    papers = [
        Paper(
            id=f"demo_paper_{uuid4().hex[:8]}",
            pmid="DEMO-PMID-001",
            doi="10.0000/demo.wmdagent.001",
            title="Demo evidence record: configure PubMed or Europe PMC search for live literature",
            abstract=(
                f"This is a demo literature placeholder for '{query_hint}'. It exists so the UI and "
                "RAG pipeline can run without network access. Replace it with live PubMed/Europe PMC "
                "results before drawing biomedical conclusions."
            ),
            journal="Demo Journal",
            publication_year=2026,
            authors=["WMD-agent Demo"],
            publication_type="Demo record",
            is_open_access=False,
            source="demo",
            url="https://europepmc.org/",
        ),
        Paper(
            id=f"demo_paper_{uuid4().hex[:8]}",
            pmid="DEMO-PMID-002",
            doi="10.0000/demo.wmdagent.002",
            title="Demo abstract-level RAG record with PMID-style citation fields",
            abstract=(
                "The system stores title, abstract, journal, publication year, DOI, and publication "
                "type, then retrieves evidence snippets and calculates an evidence confidence gate."
            ),
            journal="Demo Methods",
            publication_year=2025,
            authors=["WMD-agent Demo"],
            publication_type="Systematic review",
            is_open_access=True,
            source="demo",
            url="https://pubmed.ncbi.nlm.nih.gov/",
        ),
        Paper(
            id=f"demo_paper_{uuid4().hex[:8]}",
            pmid="DEMO-PMID-003",
            doi="10.0000/demo.wmdagent.003",
            title="Demo advanced retrieval record for HyDE, query rewriting, and CRAG fallback",
            abstract=(
                "Advanced mode expands the user question into multiple retrieval queries, merges "
                "candidate evidence, reranks snippets, and lowers confidence when the evidence set "
                "does not directly support the answer."
            ),
            journal="Demo RAG",
            publication_year=2024,
            authors=["WMD-agent Demo"],
            publication_type="Clinical trial",
            is_open_access=True,
            source="demo",
            url="https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/",
        ),
    ]
    return papers[:max_results]


def _europe_pmc_to_paper(item: dict) -> Paper:
    year = _safe_int((item.get("pubYear") or "")[:4])
    authors = []
    author_text = item.get("authorString") or ""
    if author_text:
        authors = [author.strip() for author in author_text.rstrip(".").split(",")[:8]]
    return Paper(
        id=f"paper_{item.get('id') or uuid4().hex[:12]}",
        pmid=item.get("pmid"),
        pmcid=item.get("pmcid"),
        doi=item.get("doi"),
        title=item.get("title") or "Untitled",
        abstract=item.get("abstractText") or "",
        journal=item.get("journalTitle"),
        publication_year=year,
        authors=authors,
        mesh_terms=[],
        publication_type=item.get("pubType"),
        is_open_access=(item.get("isOpenAccess") or "N").upper() == "Y",
        source="europe_pmc",
        url=f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}",
    )


def _pubmed_query(query: str, filters: SearchFilters) -> str:
    clauses = [query]
    if filters.year_from:
        year_to = filters.year_to or 3000
        clauses.append(f'("{filters.year_from}"[Date - Publication] : "{year_to}"[Date - Publication])')
    if filters.open_access_only:
        clauses.append("free full text[sb]")
    if filters.study_type:
        type_clause = " OR ".join(f'"{item}"[Publication Type]' for item in filters.study_type)
        clauses.append(f"({type_clause})")
    return " AND ".join(clauses)


def _pubmed_xml_to_papers(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find(".//MedlineCitation/PMID"))
        title = _text(article.find(".//ArticleTitle")) or "Untitled"
        abstract = _abstract_text(article)
        journal = _text(article.find(".//Journal/Title"))
        year = _pubmed_year(article)
        authors = _pubmed_authors(article)
        publication_types = [
            (node.text or "").strip()
            for node in article.findall(".//PublicationTypeList/PublicationType")
            if (node.text or "").strip()
        ]
        doi = None
        pmcid = None
        for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = (article_id.attrib.get("IdType") or "").lower()
            if id_type == "doi":
                doi = article_id.text
            elif id_type == "pmc":
                pmcid = article_id.text
        papers.append(
            Paper(
                id=f"paper_{pmid or uuid4().hex[:12]}",
                pmid=pmid,
                pmcid=pmcid,
                doi=doi,
                title=title,
                abstract=abstract,
                journal=journal,
                publication_year=year,
                authors=authors,
                mesh_terms=[],
                publication_type=", ".join(publication_types[:3]) or None,
                is_open_access=bool(pmcid),
                source="pubmed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            )
        )
    return papers


def _abstract_text(article: ET.Element) -> str:
    parts = []
    for node in article.findall(".//Abstract/AbstractText"):
        label = node.attrib.get("Label")
        text = " ".join("".join(node.itertext()).split())
        if text:
            parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts)


def _pubmed_year(article: ET.Element) -> int | None:
    for path in [
        ".//Article/Journal/JournalIssue/PubDate/Year",
        ".//PubmedData/History/PubMedPubDate/Year",
        ".//MedlineCitation/DateCompleted/Year",
    ]:
        year = _safe_int(_text(article.find(path)) or "")
        if year:
            return year
    medline_date = _text(article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate")) or ""
    return _safe_int(medline_date[:4])


def _pubmed_authors(article: ET.Element) -> list[str]:
    authors = []
    for author in article.findall(".//AuthorList/Author")[:8]:
        collective = _text(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        last = _text(author.find("LastName"))
        initials = _text(author.find("Initials"))
        if last:
            authors.append(f"{last} {initials}".strip())
    return authors


def _dedupe_papers(papers: list[Paper]) -> list[Paper]:
    merged: dict[str, Paper] = {}
    for paper in papers:
        key = paper.pmid or paper.doi or paper.pmcid or paper.id
        current = merged.get(key)
        if not current:
            merged[key] = paper
            continue
        if len(paper.abstract or "") > len(current.abstract or ""):
            merged[key] = paper
    return list(merged.values())


def _text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    text = " ".join("".join(node.itertext()).split())
    return text or None


def _safe_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
