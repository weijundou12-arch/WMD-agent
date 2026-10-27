from app.core.config import Settings
from app.rag.pipeline import MedicalRAGPipeline
from app.schemas.chat import ChatRequest, RouteDecision
from app.search.pubmed import LiteratureSearchClient


class EmptyLiteratureClient:
    async def search(self, query, max_results=10, filters=None):
        return []


async def test_medical_rag_does_not_answer_from_demo_papers():
    pipeline = MedicalRAGPipeline(literature_client=EmptyLiteratureClient())
    request = ChatRequest(
        question="司美格鲁肽会不会影响骨密度？",
        mode="medical_rag",
        retrieval_level="advanced",
    )
    decision = RouteDecision(
        query_type="medical_literature_rag",
        need_web_search=False,
        need_pubmed=True,
        need_fulltext=False,
        risk_level="medical_high_stakes",
        language="zh",
        rationale="test",
    )

    response = await pipeline.ask(request, decision)

    assert response.confidence == "insufficient"
    assert response.evidence == []
    assert "PubMed / Europe PMC" in response.answer
    assert "不会仅凭模型记忆" not in response.answer
    assert any(step.name.startswith("authoritative_source_audit") for step in response.trace)


async def test_medical_rag_uses_configured_direct_return_threshold():
    settings = Settings(rag_confidence_threshold=0.68)
    pipeline = MedicalRAGPipeline(
        literature_client=EmptyLiteratureClient(),
        settings=settings,
    )
    request = ChatRequest(
        question="HPV 与 sarcopenia 有哪些研究证据？",
        mode="medical_rag",
        retrieval_level="advanced",
    )
    decision = RouteDecision(
        query_type="medical_literature_rag",
        need_web_search=False,
        need_pubmed=True,
        need_fulltext=False,
        risk_level="medical_high_stakes",
        language="zh",
        rationale="test",
    )

    response = await pipeline.ask(request, decision)

    first_gate = next(step for step in response.trace if step.name == "evidence_gate_round_1")
    assert first_gate.metadata["threshold"] == 0.68


async def test_literature_client_returns_empty_when_live_sources_fail(monkeypatch):
    client = LiteratureSearchClient()

    async def fail_europe(*args, **kwargs):
        raise RuntimeError("offline")

    async def fail_pubmed(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(client, "_search_europe_pmc", fail_europe)
    monkeypatch.setattr(client, "_search_pubmed", fail_pubmed)

    results = await client.search("semaglutide bone mineral density", max_results=5)

    assert results == []
