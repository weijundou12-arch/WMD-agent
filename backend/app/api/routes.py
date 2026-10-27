from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.agents.context import contextualize_question
from app.agents.router import QueryRouter
from app.agents.web_search_agent import WebSearchAgent
from app.rag.confidence import (
    calculate_evidence_confidence,
    confidence_label,
    confidence_limitations,
)
from app.rag.pipeline import MedicalRAGPipeline
from app.rag.retrieval import paper_to_chunks
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    EvalRun,
    IngestRequest,
    IngestResponse,
    PubMedSearchRequest,
    WebSearchRequest,
)
from app.search.pubmed import LiteratureSearchClient
from app.search.web import WebSearchClient
from app.services.answering import synthesize_answer
from app.services.store import new_trace_id, store

router = APIRouter()
query_router = QueryRouter()
medical_pipeline = MedicalRAGPipeline()
web_agent = WebSearchAgent()
literature_client = LiteratureSearchClient()
web_client = WebSearchClient()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "wmd-agent-backend"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    contextual_question, _, _ = contextualize_question(request.question, request.conversation_history)
    decision = query_router.route(contextual_question, request.mode, request.language)
    if decision.query_type == "medical_literature_rag":
        response = await medical_pipeline.ask(request, decision)
    elif decision.query_type == "web_search":
        response = await web_agent.answer(request, decision)
    elif decision.query_type == "safe_response":
        response = await _safe_response(request, decision)
    else:
        response = await _hybrid_response(request, decision)
    return store.add_run(response)


@router.post("/search/web")
async def search_web(request: WebSearchRequest):
    return {
        "query": request.query,
        "results": await web_client.search(request.query, request.max_results),
    }


@router.post("/search/pubmed")
async def search_pubmed(request: PubMedSearchRequest):
    papers = await literature_client.search(request.query, request.max_results, request.filters)
    for paper in papers:
        store.add_paper(paper)
    return {"query": request.query, "results": papers}


@router.post("/rag/ask", response_model=ChatResponse)
async def rag_ask(request: ChatRequest) -> ChatResponse:
    forced = request.model_copy(update={"mode": "medical_rag"})
    contextual_question, _, _ = contextualize_question(forced.question, forced.conversation_history)
    decision = query_router.route(contextual_question, forced.mode, forced.language)
    response = await medical_pipeline.ask(forced, decision)
    return store.add_run(response)


@router.post("/medical/ask", response_model=ChatResponse)
async def medical_ask(request: ChatRequest) -> ChatResponse:
    forced = request.model_copy(update={"mode": "medical_rag"})
    contextual_question, _, _ = contextualize_question(forced.question, forced.conversation_history)
    decision = query_router.route(contextual_question, forced.mode, forced.language)
    response = await medical_pipeline.ask(forced, decision)
    return store.add_run(response)


@router.post("/web/ask", response_model=ChatResponse)
async def web_ask(request: ChatRequest) -> ChatResponse:
    forced = request.model_copy(update={"mode": "web_search"})
    contextual_question, _, _ = contextualize_question(forced.question, forced.conversation_history)
    decision = query_router.route(contextual_question, forced.mode, forced.language)
    response = await web_agent.answer(forced, decision)
    return store.add_run(response)


@router.post("/rag/ingest", response_model=IngestResponse)
async def rag_ingest(request: IngestRequest) -> IngestResponse:
    status = "updated" if store.get_paper(request.paper.id) else "stored"
    store.add_paper(request.paper)
    chunks = paper_to_chunks(request.paper, request.full_text)
    return IngestResponse(paper_id=request.paper.id, chunk_count=len(chunks), status=status)


@router.get("/papers")
async def list_papers():
    return {"results": store.list_papers()}


@router.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    paper = store.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.get("/evidence/{answer_id}")
async def get_evidence(answer_id: str):
    run = store.get_run(answer_id)
    if not run:
        raise HTTPException(status_code=404, detail="Answer trace not found")
    return {"answer_id": answer_id, "evidence": run.evidence}


@router.get("/traces/{run_id}")
async def get_trace(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {
        "trace_id": run.trace_id,
        "route_decision": run.route_decision,
        "trace": run.trace,
        "latency_ms": run.latency_ms,
        "confidence_score": run.confidence_score,
    }


@router.get("/eval/runs")
async def list_eval_runs():
    return {"results": store.list_eval_runs()}


@router.post("/eval/run", response_model=EvalRun)
async def create_eval_run() -> EvalRun:
    runs = store.list_runs()
    if runs:
        mean_latency = sum(run.latency_ms for run in runs) / len(runs)
        citation_precision = sum(1 for run in runs if run.evidence) / len(runs)
        faithfulness = sum(run.confidence_score for run in runs) / len(runs)
        answer_relevancy = sum(1 for run in runs if run.confidence != "insufficient") / len(runs)
    else:
        mean_latency = 0.0
        citation_precision = 0.0
        faithfulness = 0.0
        answer_relevancy = 0.0
    eval_run = EvalRun(
        id=new_trace_id("eval"),
        created_at=datetime.now(UTC),
        total_runs=len(runs),
        faithfulness=round(faithfulness, 3),
        citation_precision=round(citation_precision, 3),
        answer_relevancy=round(answer_relevancy, 3),
        mean_latency_ms=round(mean_latency, 1),
        notes=[
            "MVP metric estimates are trace-derived placeholders.",
            "Wire RAGAS or DeepEval here for dataset-based evaluation.",
        ],
    )
    return store.add_eval_run(eval_run)


async def _hybrid_response(request: ChatRequest, decision) -> ChatResponse:
    medical = await medical_pipeline.ask(request, decision)
    web = await web_agent.answer(request, decision)
    evidence = sorted(
        [*medical.evidence, *web.evidence],
        key=lambda item: item.rerank_score,
        reverse=True,
    )[:8]
    score = calculate_evidence_confidence(evidence)
    label = confidence_label(score, len(evidence))
    limitations = confidence_limitations(label, len(evidence))
    answer = synthesize_answer(request.question, evidence, label, limitations, request.language)
    return ChatResponse(
        answer=answer,
        confidence=label,
        confidence_score=score,
        route=decision.query_type,
        evidence=evidence,
        limitations=limitations,
        trace_id=new_trace_id(),
        route_decision=decision,
        trace=[
            *medical.trace,
            *web.trace,
        ],
        latency_ms=medical.latency_ms + web.latency_ms,
        model_version="deterministic-hybrid-evidence-synthesizer-v1",
    )


async def _safe_response(request: ChatRequest, decision) -> ChatResponse:
    hybrid = await _hybrid_response(request, decision)
    safe_prefix = (
        "这是一个高风险医学问题，我不能把检索结果转换成个人诊断或治疗指令。"
        "下面只总结可追溯证据，并建议由合格临床医生结合个人病史判断。\n\n"
    )
    return hybrid.model_copy(update={"answer": safe_prefix + hybrid.answer})
