from app.rag.confidence import calculate_evidence_confidence, confidence_label
from app.schemas.chat import EvidenceItem


def test_confidence_gate_requires_score_and_evidence_count():
    evidence = [
        EvidenceItem(
            id=f"e{i}",
            title=f"Evidence {i}",
            snippet="direct supporting evidence",
            support_level="direct",
            retrieval_score=0.8,
            rerank_score=0.85,
            source_quality_score=0.9,
            year=2025,
        )
        for i in range(3)
    ]

    score = calculate_evidence_confidence(evidence)

    assert score >= 0.75
    assert confidence_label(score, len(evidence)) == "strong"
