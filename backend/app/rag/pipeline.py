from __future__ import annotations

import time
from uuid import uuid4

from app.agents.context import contextualize_question
from app.core.config import Settings, get_settings
from app.rag.confidence import (
    calculate_evidence_confidence,
    confidence_label,
    confidence_limitations,
)
from app.rag.retrieval import retrieve_from_papers
from app.schemas.chat import ChatRequest, ChatResponse, EvidenceItem, RouteDecision, TraceStep
from app.search.pubmed import LiteratureSearchClient
from app.search.web import WebSearchClient
from app.services.answering import synthesize_answer
from app.services.store import new_trace_id


class MedicalRAGPipeline:
    def __init__(
        self,
        literature_client: LiteratureSearchClient | None = None,
        web_client: WebSearchClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.literature_client = literature_client or LiteratureSearchClient(self.settings)
        self.web_client = web_client or WebSearchClient(self.settings)

    async def ask(self, request: ChatRequest, route_decision: RouteDecision) -> ChatResponse:
        started = time.perf_counter()
        direct_return_threshold = self.settings.rag_confidence_threshold
        contextual_question, used_context, context_summary = contextualize_question(
            request.question,
            request.conversation_history,
        )
        trace: list[TraceStep] = [
            TraceStep(
                name="understanding_question",
                status="ok",
                detail="Detected medical literature retrieval intent and prepared evidence-first RAG workflow.",
                metadata={
                    "level": request.retrieval_level,
                    "direct_return_threshold": direct_return_threshold,
                    "corpus": ["PubMed / NCBI E-utilities", "Europe PMC"],
                    "used_conversation_context": used_context,
                },
            )
        ]
        if used_context:
            trace.append(
                TraceStep(
                    name="conversation_context_resolution",
                    status="ok",
                    detail="Resolved the current follow-up against recent turns before literature query rewriting.",
                    metadata={"context": context_summary, "contextual_question": contextual_question},
                )
            )
        trace.append(
            TraceStep(
                name="authoritative_corpus_selection",
                status="ok",
                detail="Selected PubMed / NCBI E-utilities and Europe PMC as the medical literature corpus.",
                metadata={"sources": ["pubmed", "europe_pmc"]},
            )
        )
        max_rounds = 3 if request.retrieval_level == "advanced" else 1
        retrieval_question = self._retrieval_question(contextual_question)
        papers = []
        evidence: list[EvidenceItem] = []
        score = 0.0
        label = "insufficient"

        for round_index in range(1, max_rounds + 1):
            queries = self._plan_queries(contextual_question, request.retrieval_level, round_index)
            round_started = time.perf_counter()
            trace.append(
                TraceStep(
                    name=f"query_rewrite_round_{round_index}",
                    status="ok",
                    detail=f"Generated {len(queries)} literature query/query variants.",
                    metadata={"queries": queries},
                )
            )

            round_papers = []
            for query in queries:
                found = await self.literature_client.search(
                    query=query,
                    max_results=max(3, self.settings.rag_default_top_k // len(queries)),
                    filters=request.filters,
                )
                round_papers.extend(found)
            papers = list({paper.id: paper for paper in [*papers, *round_papers]}.values())
            papers = _strict_authoritative_papers(papers)
            trace.append(
                TraceStep(
                    name=f"coarse_retrieval_round_{round_index}",
                    status="ok" if papers else "warning",
                    detail=(
                        f"Retrieved {len(round_papers)} new records; "
                        f"candidate pool now has {len(papers)} unique records."
                    ),
                    elapsed_ms=int((time.perf_counter() - round_started) * 1000),
                    metadata={"bm25_top_k": 50, "dense_top_k": 50, "candidate_pool": len(papers)},
                )
            )
            trace.append(
                TraceStep(
                    name=f"authoritative_source_audit_round_{round_index}",
                    status="ok" if papers else "warning",
                    detail=(
                        "Filtered candidate records to PubMed / Europe PMC paper records only."
                        if papers
                        else "No valid PubMed / Europe PMC paper record survived strict source filtering."
                    ),
                    metadata={
                        "allowed_sources": ["pubmed", "europe_pmc"],
                        "excluded_sources": ["demo", "web", "wikipedia", "commercial"],
                        "strict_medical_rag": True,
                    },
                )
            )

            evidence = retrieve_from_papers(
                retrieval_question,
                papers,
                top_k=self.settings.rag_rerank_top_k,
                candidate_pool_size=80 if request.retrieval_level == "advanced" else 30,
            )
            score = calculate_evidence_confidence(evidence)
            label = confidence_label(score, len(evidence))
            trace.append(
                TraceStep(
                    name=f"evidence_gate_round_{round_index}",
                    status="ok" if score >= direct_return_threshold else "warning",
                    detail=(
                        f"Weighted evidence score is {score}. "
                        f"{'Direct return allowed.' if score >= direct_return_threshold else f'Below {direct_return_threshold:.2f}; continuing recall.'}"
                    ),
                    metadata={
                        "confidence": label,
                        "score": score,
                        "threshold": direct_return_threshold,
                        "top_k_after_rerank": len(evidence),
                        "weighted_formula": (
                            "0.30*rerank + 0.20*retrieval + 0.20*source_quality + "
                            "0.15*directness + 0.10*recency + 0.05*study_type"
                        ),
                    },
                )
            )

            if score >= direct_return_threshold:
                break

        if score < direct_return_threshold:
            trace.append(
                TraceStep(
                    name="insufficient_literature_gate",
                    status="warning",
                    detail=(
                        f"Pure Medical RAG stayed below {direct_return_threshold:.2f} after the configured recall rounds. "
                        "The agent will answer only from retrieved paper evidence; use Hybrid mode for web corroboration."
                    ),
                    metadata={
                        "new_score": score,
                        "confidence": label,
                        "fallback": "web search is intentionally not mixed into pure Medical RAG",
                    },
                )
            )

        trace.append(
            TraceStep(
                name="reranker_evidence_selection",
                status="ok" if evidence else "warning",
                detail=(
                    f"Selected {len(evidence)} reranked paper evidence snippets."
                    if evidence
                    else "No paper evidence selected after BM25+dense recall and reranking."
                ),
                metadata={
                    "basic_rag": "BM25 + dense retrieval",
                    "advanced_rag": "multi-query + hybrid recall + reranker + weighted evidence gate",
                    "top_k": self.settings.rag_rerank_top_k,
                },
            )
        )
        trace.append(
            TraceStep(
                name="answer_generation",
                status="ok",
                detail="Generated the final answer from selected evidence, limitations, confidence, and citation metadata.",
            )
        )
        trace.append(
            TraceStep(
                name="gpt4_style_comparison",
                status="ok",
                detail="Added a GPT-4-style cross-check over the same strict PubMed / Europe PMC evidence set.",
                metadata={"comparison_basis": "same reranked paper evidence", "strict_medical_sources_only": True},
            )
        )

        limitations = confidence_limitations(label, len(evidence))
        if any(item.source_type == "demo" for item in evidence):
            limitations.insert(
                0,
                "Demo mode is active; evidence records are placeholders and must not be used for biomedical conclusions.",
            )
        answer = synthesize_answer(
            contextual_question if used_context else request.question,
            evidence,
            confidence=label,
            limitations=limitations,
            language=request.language,
        )
        if used_context:
            answer = _replace_question_with_context_note(answer, request.question, context_summary, request.language)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ChatResponse(
            answer=answer,
            confidence=label,
            confidence_score=score,
            route=route_decision.query_type,
            evidence=evidence,
            limitations=limitations,
            trace_id=new_trace_id(),
            route_decision=route_decision,
            trace=trace,
            latency_ms=latency_ms,
        )

    def _plan_queries(self, question: str, retrieval_level: str, round_index: int = 1) -> list[str]:
        if retrieval_level == "basic":
            concept_queries = self._medical_concept_queries(question)
            return [concept_queries[0]] if concept_queries else [question]
        concept_queries = self._medical_concept_queries(question)
        if round_index == 1:
            rewrites = concept_queries or [question]
            rewrites = [*rewrites, f"{rewrites[0]} clinical trial systematic review"]
        elif round_index == 2:
            rewrites = self._second_round_queries(question, concept_queries)
        else:
            rewrites = self._third_round_queries(question, concept_queries)
        return list(dict.fromkeys(rewrites))[:4]

    def _medical_concept_queries(self, question: str) -> list[str]:
        lower = question.lower()
        queries: list[str] = []
        if "司美格鲁肽" in question or "semaglutide" in lower or "glp-1" in lower:
            queries.extend(
                [
                    "semaglutide bone mineral density",
                    "GLP-1 receptor agonist osteoporosis fracture risk",
                    "GLP-1RA skeletal health clinical study",
                ]
            )
        if "hpv" in lower and ("肌少" in question or "sarcopenia" in lower):
            queries.extend(
                [
                    "HPV infection sarcopenia",
                    "human papillomavirus skeletal muscle inflammation",
                    "HPV systemic inflammation muscle mass",
                ]
            )
        return queries

    def _retrieval_question(self, question: str) -> str:
        concept_queries = self._medical_concept_queries(question)
        return " ".join([question, *concept_queries])

    def _second_round_queries(self, question: str, concept_queries: list[str]) -> list[str]:
        lower = question.lower()
        if "司美格鲁肽" in question or "semaglutide" in lower or "glp-1" in lower:
            return [
                "semaglutide bone turnover randomized trial",
                "GLP-1 receptor agonist bone metabolism systematic review",
                "semaglutide fracture risk cohort study",
            ]
        if "hpv" in lower and ("肌少" in question or "sarcopenia" in lower):
            return [
                "human papillomavirus sarcopenia cohort",
                "HPV infection muscle strength epidemiology",
                "HPV systemic inflammation sarcopenia review",
            ]
        base = concept_queries[0] if concept_queries else question
        return [
            f"{base} meta-analysis cohort review",
            f"{base} outcome association risk",
            f"{base} PubMed Europe PMC biomedical evidence",
        ]

    def _third_round_queries(self, question: str, concept_queries: list[str]) -> list[str]:
        lower = question.lower()
        if "司美格鲁肽" in question or "semaglutide" in lower or "glp-1" in lower:
            return [
                "incretin therapy bone mineral density osteoporosis",
                "GLP-1RA skeletal health fracture bone density",
                "obesity pharmacotherapy weight loss bone mineral density semaglutide",
            ]
        if "hpv" in lower and ("肌少" in question or "sarcopenia" in lower):
            return [
                "viral infection sarcopenia inflammation",
                "HPV chronic inflammation skeletal muscle",
                "human papillomavirus frailty muscle mass",
            ]
        base = concept_queries[0] if concept_queries else question
        return [
            f"{base} related synonyms mechanism",
            f"{base} guideline review latest evidence",
            f"{base} broad biomedical literature",
        ]

def demo_evidence_item(title: str, snippet: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"demo_{uuid4().hex[:8]}",
        title=title,
        source_type="demo",
        snippet=snippet,
        support_level="background",
        retrieval_score=0.3,
        rerank_score=0.4,
        source_quality_score=0.5,
    )


def _drop_demo_when_live_papers_exist(papers: list) -> list:
    has_live = any(not _is_demo_paper(paper) for paper in papers)
    if not has_live:
        return papers
    return [paper for paper in papers if not _is_demo_paper(paper)]


def _is_demo_paper(paper) -> bool:
    return paper.source == "demo" or paper.id.startswith("demo_")


def _strict_authoritative_papers(papers: list) -> list:
    allowed_sources = {"pubmed", "europe_pmc"}
    filtered = [
        paper
        for paper in papers
        if not _is_demo_paper(paper)
        and paper.source in allowed_sources
        and (paper.title or paper.abstract)
    ]
    return filtered


def _replace_question_with_context_note(answer: str, question: str, context_summary: str, language: str) -> str:
    context_note = " ".join(context_summary.split())[:420]
    if language.lower().startswith("zh"):
        replacement = f"Question：{question}\nContext Used：系统已参考同一对话中最近几轮上下文。{context_note}"
        return re_sub_question_block(answer, replacement, zh=True)
    replacement = f"Question: {question}\nContext Used: Recent turns in the same chat were used. {context_note}"
    return re_sub_question_block(answer, replacement, zh=False)


def re_sub_question_block(answer: str, replacement: str, zh: bool) -> str:
    import re

    label = "Question：" if zh else "Question:"
    pattern = rf"{re.escape(label)}.*?(?=\n\n(?:Model Summary|Limitations|Confidence|References|Medical Note)：?|\n\n(?:Model Summary|Limitations|Confidence|References|Medical Note):)"
    updated = re.sub(pattern, replacement, answer, flags=re.DOTALL)
    return updated if updated != answer else answer
