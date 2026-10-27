from __future__ import annotations

import math
import re
from collections import Counter
from uuid import uuid4

from app.schemas.chat import EvidenceItem, Paper


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9\u4e00-\u9fff\-]+")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_PATTERN.findall(text):
        lower = token.lower()
        tokens.append(lower)
        cjk_chars = CJK_PATTERN.findall(token)
        if cjk_chars:
            tokens.extend(cjk_chars)
            tokens.extend(
                "".join(cjk_chars[index : index + 2])
                for index in range(0, max(len(cjk_chars) - 1, 0))
            )
    return tokens


def split_chunks(text: str, max_words: int = 160) -> list[str]:
    words = text.split()
    if not words:
        return []
    return [" ".join(words[index : index + max_words]) for index in range(0, len(words), max_words)]


def retrieve_from_papers(
    question: str,
    papers: list[Paper],
    top_k: int = 8,
    candidate_pool_size: int = 80,
) -> list[EvidenceItem]:
    query_tokens = tokenize(question)
    corpus: list[tuple[Paper, str, str]] = []
    for paper in papers:
        combined = f"{paper.title}\n{paper.abstract}".strip()
        chunks = split_chunks(combined) or [combined]
        for index, chunk in enumerate(chunks):
            section = "Abstract" if index == 0 else f"Abstract chunk {index + 1}"
            corpus.append((paper, section, chunk))

    scored: list[EvidenceItem] = []
    for paper, section, chunk in corpus:
        is_demo = paper.id.startswith("demo_") or paper.source == "demo"
        bm25_score = _lexical_similarity(query_tokens, tokenize(chunk))
        dense_score = _dense_proxy_similarity(question, f"{paper.title} {chunk}")
        retrieval_score = min(1.0, 0.55 * bm25_score + 0.45 * dense_score)
        if retrieval_score <= 0:
            retrieval_score = 0.08
        rerank_score = _rerank_score(question, paper, chunk, retrieval_score)
        scored.append(
            EvidenceItem(
                id=paper.id,
                title=paper.title,
                source_type="demo" if is_demo else "paper",
                url=paper.url,
                pmid=paper.pmid,
                pmcid=paper.pmcid,
                doi=paper.doi,
                journal=paper.journal,
                year=paper.publication_year,
                study_type=paper.publication_type,
                snippet=_trim_snippet(chunk),
                section=section,
                support_level="background" if is_demo else "direct" if rerank_score >= 0.62 else "background",
                retrieval_score=round(retrieval_score, 3),
                rerank_score=round(rerank_score, 3),
                source_quality_score=_paper_quality_score(paper),
            )
        )

    coarse_pool = sorted(scored, key=lambda item: item.retrieval_score, reverse=True)[:candidate_pool_size]
    reranked = sorted(coarse_pool, key=lambda item: item.rerank_score, reverse=True)
    best_by_paper: dict[str, EvidenceItem] = {}
    for item in reranked:
        key = item.pmid or item.doi or item.id
        if key not in best_by_paper:
            best_by_paper[key] = item

    deduped = list(best_by_paper.values())
    relevant = [
        item
        for item in deduped
        if item.source_type == "demo" or item.retrieval_score >= 0.09 or item.rerank_score >= 0.25
    ]
    return (relevant or deduped)[:top_k]


def retrieve_from_web(question: str, sources: list[EvidenceItem], top_k: int = 8) -> list[EvidenceItem]:
    query_tokens = tokenize(question)
    primary_place = _primary_chinese_place(question)
    rescored: list[EvidenceItem] = []
    for source in sources:
        if source.id.startswith("web_unavailable_"):
            rescored.append(
                source.model_copy(
                    update={
                        "retrieval_score": 0.0,
                        "rerank_score": 0.0,
                        "support_level": "background",
                    }
                )
            )
            continue
        text = f"{source.title} {source.snippet} {source.url or ''}"
        lexical_score = _lexical_similarity(query_tokens, tokenize(text))
        semantic_score = _dense_proxy_similarity(question, text)
        locality_score = _locality_score(question, text)
        provider_rank_signal = min(source.retrieval_score, 1.0)
        exact_place_title_bonus = 0.28 if _is_exact_place_title(source.title, primary_place) else 0.0
        retrieval_score = min(
            1.0,
            0.42 * lexical_score
            + 0.32 * semantic_score
            + 0.18 * locality_score
            + 0.08 * provider_rank_signal
            + exact_place_title_bonus
        )
        score = min(1.0, 0.36 * source.source_quality_score + 0.64 * retrieval_score + exact_place_title_bonus)
        rescored.append(
            source.model_copy(
                update={
                    "retrieval_score": round(retrieval_score, 3),
                    "rerank_score": round(score, 3),
                    "support_level": _web_support_level(retrieval_score, score),
                }
            )
        )
    relevant = [
        item
        for item in rescored
        if item.retrieval_score >= 0.12
        or (item.source_quality_score >= 0.90 and item.rerank_score >= 0.30)
        or item.id.startswith("web_unavailable_")
    ]
    ranked = relevant or rescored
    return sorted(ranked, key=lambda item: item.rerank_score, reverse=True)[:top_k]


def paper_to_chunks(paper: Paper, full_text: str | None = None) -> list[dict[str, str | int]]:
    base = full_text or paper.abstract or paper.title
    chunks = split_chunks(base, max_words=220)
    return [
        {
            "id": f"chunk_{uuid4().hex[:12]}",
            "paper_id": paper.id,
            "section": "Full Text" if full_text else "Abstract",
            "chunk_text": chunk,
            "chunk_index": index,
            "token_count": len(tokenize(chunk)),
            "contextual_header": f"Paper: {paper.title}\nJournal: {paper.journal or 'Unknown'}",
        }
        for index, chunk in enumerate(chunks)
    ]


def _lexical_similarity(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    query_counts = Counter(query_tokens)
    doc_counts = Counter(doc_tokens)
    overlap = sum(min(query_counts[token], doc_counts[token]) for token in query_counts)
    coverage = overlap / max(len(set(query_tokens)), 1)
    density = overlap / math.sqrt(max(len(doc_tokens), 1))
    return min(1.0, 0.75 * coverage + 0.25 * density)


def _dense_proxy_similarity(question: str, document: str) -> float:
    query_tokens = set(tokenize(question))
    doc_tokens = set(tokenize(document))
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = len(query_tokens & doc_tokens) / max(len(query_tokens | doc_tokens), 1)
    synonym_bonus = _synonym_overlap(question, document)
    return min(1.0, overlap + synonym_bonus)


def _synonym_overlap(question: str, document: str) -> float:
    lower_question = question.lower()
    lower_doc = document.lower()
    concepts = [
        ("司美格鲁肽", ["semaglutide", "glp-1", "glp-1ra"]),
        ("骨密度", ["bone mineral density", "bmd", "osteoporosis", "fracture"]),
        ("肌少症", ["sarcopenia", "muscle mass", "skeletal muscle"]),
        ("指南", ["guideline", "recommendation", "consensus"]),
        ("价格", ["price", "cost", "reimbursement"]),
        ("德国", ["germany", "deutschland", "german", "bfarm", "g-ba", "apotheke"]),
        ("多少钱", ["price", "cost", "preis", "reimbursement", "copay"]),
        ("目前", ["current", "latest", "2026", "2025", "now"]),
        ("申请", ["application", "apply", "admission", "requirements", "qualification assessment", "campo"]),
        ("学校", ["university", "facts and figures", "degree programs", "profile"]),
        ("大学", ["university", "hochschule", "institute of technology", "degree programmes"]),
        ("清华", ["tsinghua", "tsinghua university"]),
        ("清华大学", ["tsinghua", "tsinghua university"]),
        ("北京大学", ["peking university", "pku"]),
        ("北大", ["peking university", "pku"]),
        ("纽伦堡", ["nuremberg", "nürnberg", "nuernberg"]),
        ("埃尔朗根", ["erlangen"]),
        ("专业", ["degree program", "study program", "master", "msc", "m.sc"]),
        ("人工智能", ["artificial intelligence", "ai", "machine learning"]),
        ("fau", ["friedrich-alexander", "erlangen", "nürnberg", "nuremberg", "fau"]),
    ]
    bonus = 0.0
    for zh_term, aliases in concepts:
        if zh_term in lower_question and any(alias in lower_doc for alias in aliases):
            bonus += 0.12
        if any(alias in lower_question for alias in aliases) and zh_term in lower_doc:
            bonus += 0.12
    return min(bonus, 0.36)


def _locality_score(question: str, document: str) -> float:
    lower_question = question.lower()
    lower_doc = document.lower()
    score = 0.0
    if ("德国" in question or "germany" in lower_question or "deutschland" in lower_question) and any(
        term in lower_doc for term in ["germany", "deutschland", ".de", "bfarm", "g-ba", "apotheke"]
    ):
        score += 0.8
    if ("司美格鲁肽" in question or "semaglutide" in lower_question) and any(
        term in lower_doc for term in ["semaglutide", "semaglutid", "ozempic", "wegovy"]
    ):
        score += 0.2
    if "fau" in lower_question and any(
        term in lower_doc for term in ["fau", "friedrich-alexander", "erlangen", "nürnberg", "nuremberg"]
    ):
        score += 0.65
    if ("纽伦堡" in question or "nuremberg" in lower_question or "nürnberg" in lower_question) and any(
        term in lower_doc for term in ["nuremberg", "nürnberg", "nuernberg", "erlangen", "fau", "hochschule"]
    ):
        score += 0.55
    if ("清华" in question or "tsinghua" in lower_question) and any(
        term in lower_doc for term in ["tsinghua", "清华", "tsinghua.edu.cn"]
    ):
        score += 0.70
    for place in re.findall(r"[\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡)", question):
        if place and place in document:
            score += 0.65
    if "博兴" in question and "博兴" in document:
        score += 0.65
    if "山东" in question and any(term in document for term in ["山东", "shandong", "sd.gov.cn"]):
        score += 0.20
    if "滨州" in question and any(term in document for term in ["滨州", "binzhou"]):
        score += 0.20
    if any(term in question for term in ["申请", "条件"]) and any(
        term in lower_doc for term in ["application", "apply", "admission", "requirements", "qualification assessment"]
    ):
        score += 0.25
    if ("ai" in lower_question or "人工智能" in question) and any(
        term in lower_doc for term in ["artificial intelligence", "machine learning", "ai"]
    ):
        score += 0.20
    return min(score, 1.0)


def _web_support_level(retrieval_score: float, rerank_score: float) -> str:
    if retrieval_score >= 0.50 and rerank_score >= 0.62:
        return "direct"
    if retrieval_score >= 0.30:
        return "partial"
    if retrieval_score >= 0.12:
        return "background"
    return "indirect"


def _primary_chinese_place(question: str) -> str:
    compact = re.sub(r"[，。！？?：:；;、,.\s]", "", question)
    for phrase in ["介绍一下", "介绍下", "介绍", "说说", "了解一下", "请问", "中国", "中华人民共和国", "山东省", "山东"]:
        compact = compact.replace(phrase, "")
    match = re.search(r"[\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡)", compact)
    return match.group(0) if match else ""


def _is_exact_place_title(title: str, place: str) -> bool:
    if not place:
        return False
    normalized = title.replace("中文维基百科：", "").replace("Wikipedia:", "").strip()
    return normalized == place or normalized == f"{place}人民政府门户网站" or normalized == f"{place}人民政府"


def _rerank_score(question: str, paper: Paper, chunk: str, retrieval_score: float) -> float:
    title_bonus = 0.12 if set(tokenize(question)) & set(tokenize(paper.title)) else 0.0
    abstract_bonus = 0.08 if len(chunk) > 120 else 0.02
    study_bonus = 0.08 if (paper.publication_type or "").lower() in {
        "clinical trial",
        "randomized controlled trial",
        "meta-analysis",
        "systematic review",
    } else 0.0
    return min(1.0, retrieval_score + title_bonus + abstract_bonus + study_bonus)


def _paper_quality_score(paper: Paper) -> float:
    if paper.source == "demo" or paper.id.startswith("demo_"):
        return 0.35
    publication_type = (paper.publication_type or "").lower()
    if "meta" in publication_type or "systematic" in publication_type:
        return 0.92
    if "randomized" in publication_type or "clinical trial" in publication_type:
        return 0.88
    if paper.pmid or paper.doi:
        return 0.82
    if paper.source == "europe_pmc":
        return 0.78
    return 0.55


def _trim_snippet(text: str, max_chars: int = 520) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "..."
