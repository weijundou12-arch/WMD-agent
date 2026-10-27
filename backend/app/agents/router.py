from __future__ import annotations

import re

from app.schemas.chat import AgentMode, RouteDecision


CURRENT_INFO_PATTERNS = [
    r"\b(today|current|latest|recent|now|price|cost|news|policy|guideline)\b",
    r"最新",
    r"目前",
    r"现在",
    r"价格",
    r"多少钱",
    r"新闻",
    r"政策",
    r"指南",
    r"202[5-9]",
]

MEDICAL_PATTERNS = [
    r"\b(pubmed|pmid|doi|trial|cohort|meta-analysis|systematic review)\b",
    r"\b(disease|drug|therapy|diagnosis|prognosis|biomarker|clinical)\b",
    r"\b(semaglutide|glp-1|hpv|sarcopenia|osteoporosis|fracture|acl)\b",
    r"医学",
    r"疾病",
    r"药物",
    r"诊断",
    r"治疗",
    r"论文",
    r"研究",
    r"证据",
    r"指南",
    r"司美格鲁肽",
    r"骨密度",
    r"肌少症",
]

PERSONAL_CARE_PATTERNS = [
    r"\b(my|i have|should i|patient)\b",
    r"我.*(该|应该|能不能|是不是)",
    r"病人",
    r"处方",
    r"剂量",
]


class QueryRouter:
    def route(self, question: str, mode: AgentMode = "auto", language: str = "zh") -> RouteDecision:
        normalized = question.lower()
        is_current = self._matches(normalized, CURRENT_INFO_PATTERNS)
        is_medical = self._matches(normalized, MEDICAL_PATTERNS)
        is_personal = self._matches(normalized, PERSONAL_CARE_PATTERNS)

        if mode == "web_search":
            query_type = "web_search"
            need_web, need_pubmed, need_fulltext = True, False, False
            rationale = "User selected Web Search mode."
        elif mode == "medical_rag":
            query_type = "medical_literature_rag"
            need_web, need_pubmed, need_fulltext = False, True, True
            rationale = "User selected Medical RAG mode."
        elif mode == "hybrid":
            query_type = "hybrid"
            need_web, need_pubmed, need_fulltext = True, True, True
            rationale = "User selected Hybrid mode."
        elif is_personal and is_medical:
            query_type = "safe_response"
            need_web, need_pubmed, need_fulltext = True, True, False
            rationale = "Medical personal-care wording detected, so strict safety response is required."
        elif is_current and is_medical:
            query_type = "hybrid"
            need_web, need_pubmed, need_fulltext = True, True, True
            rationale = "The question is medical and time-sensitive, so both web and literature evidence are useful."
        elif is_current:
            query_type = "web_search"
            need_web, need_pubmed, need_fulltext = True, False, False
            rationale = "The question asks for current information."
        else:
            query_type = "medical_literature_rag" if is_medical else "web_search"
            need_web = not is_medical
            need_pubmed = is_medical
            need_fulltext = is_medical
            rationale = "Heuristic routing based on medical and recency signals."

        risk_level = "medical_high_stakes" if is_medical else "low"
        if is_medical and not is_personal:
            risk_level = "medical_low"

        return RouteDecision(
            query_type=query_type,
            need_web_search=need_web,
            need_pubmed=need_pubmed,
            need_fulltext=need_fulltext,
            risk_level=risk_level,
            language=language,
            rationale=rationale,
        )

    @staticmethod
    def _matches(text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
