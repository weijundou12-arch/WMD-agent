from app.agents.router import QueryRouter


def test_routes_medical_question_to_literature_rag():
    decision = QueryRouter().route("GLP-1 药物和骨密度之间有没有关系？")

    assert decision.query_type == "medical_literature_rag"
    assert decision.need_pubmed is True
    assert decision.risk_level == "medical_low"


def test_routes_current_price_to_hybrid_or_web():
    decision = QueryRouter().route("德国司美格鲁肽目前多少钱？")

    assert decision.need_web_search is True
    assert decision.query_type in {"web_search", "hybrid"}
