from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean

from app.schemas.chat import ConfidenceLabel, EvidenceItem


def calculate_evidence_confidence(evidence: list[EvidenceItem]) -> float:
    if not evidence:
        return 0.0

    sorted_items = sorted(evidence, key=lambda item: item.rerank_score, reverse=True)
    top_items = sorted_items[:5]
    rerank_score = mean([item.rerank_score for item in top_items])
    retrieval_similarity = mean([item.retrieval_score for item in top_items])
    source_quality = mean([item.source_quality_score for item in top_items])
    evidence_directness = mean([_directness_score(item.support_level) for item in top_items])
    recency = mean([_recency_score(item.year) for item in top_items])
    study_type_quality = mean([_study_type_score(item.study_type) for item in top_items])

    score = (
        0.30 * rerank_score
        + 0.20 * retrieval_similarity
        + 0.20 * source_quality
        + 0.15 * evidence_directness
        + 0.10 * recency
        + 0.05 * study_type_quality
    )
    return round(min(max(score, 0.0), 1.0), 3)


def confidence_label(score: float, evidence_count: int) -> ConfidenceLabel:
    if score >= 0.70 and evidence_count >= 3:
        return "strong"
    if score >= 0.55 and evidence_count >= 2:
        return "moderate"
    if score >= 0.40:
        return "weak"
    return "insufficient"


def confidence_limitations(label: ConfidenceLabel, evidence_count: int) -> list[str]:
    if label == "strong":
        return ["证据通过当前加权阈值，但这仍不是个人医疗诊断或治疗建议。"]
    if label == "moderate":
        return [
            "证据与问题相关，但数量、研究类型或直接性仍有限。",
            "临床决策仍需要结合指南、病史和医生判断。",
        ]
    if label == "weak":
        return [
            "召回证据较弱，系统应继续改写 query 或扩大文献召回。",
            "不要把该回答当作确定临床结论。",
        ]
    return [
        "没有召回到足以支撑可靠回答的证据。",
        "系统应避免输出实质性医学断言。",
    ]


def _recency_score(year: int | None) -> float:
    if not year:
        return 0.45
    current_year = datetime.now(UTC).year
    age = max(current_year - year, 0)
    if age <= 2:
        return 1.0
    if age <= 5:
        return 0.8
    if age <= 10:
        return 0.6
    return 0.4


def _directness_score(support_level: str) -> float:
    return {
        "direct": 1.0,
        "partial": 0.7,
        "indirect": 0.6,
        "background": 0.4,
        "conflicting": 0.2,
    }.get(support_level, 0.0)


def _study_type_score(study_type: str | None) -> float:
    normalized = (study_type or "").lower()
    if "meta" in normalized or "systematic" in normalized:
        return 1.0
    if "randomized" in normalized or "rct" in normalized or "clinical trial" in normalized:
        return 0.95
    if "prospective" in normalized and "cohort" in normalized:
        return 0.85
    if "retrospective" in normalized and "cohort" in normalized:
        return 0.75
    if "cross-sectional" in normalized:
        return 0.65
    if "narrative" in normalized or "review" in normalized:
        return 0.5
    if "case" in normalized:
        return 0.4
    if "demo" in normalized:
        return 0.2
    return 0.6
