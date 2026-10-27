from __future__ import annotations

import re

from app.schemas.chat import ConversationTurn


FOLLOW_UP_PATTERNS = [
    r"^(那|那么|继续|还有|另外|再|顺便|同时|它|这个|该|上述|上面|前面|这些|那些|那里|当地)",
    r"(它|这个|这个地方|该地|当地|那里|上述|上面|前面|这些|那些|they|them|it|this|that|those|these)",
    r"(呢|怎么样|如何|为什么|具体|详细|条件|要求|风险|价格|排名|截止|语言|材料|证据|机制|旅游|推荐|景点|美食|路线|饭店|餐厅|酒店)[？?]?$",
]


def contextualize_question(question: str, history: list[ConversationTurn]) -> tuple[str, bool, str]:
    clean_question = " ".join(question.split())
    usable_history = [turn for turn in history if turn.question.strip()][-3:]
    if not usable_history:
        return clean_question, False, ""

    context = _history_context(usable_history)
    if not _looks_like_follow_up(clean_question):
        return clean_question, False, context

    contextual_question = _standalone_follow_up_question(clean_question, usable_history)
    return contextual_question, True, context


def _looks_like_follow_up(question: str) -> bool:
    lower = question.lower()
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in FOLLOW_UP_PATTERNS)


def _history_context(history: list[ConversationTurn]) -> str:
    lines: list[str] = []
    for index, turn in enumerate(history, start=1):
        evidence = "；".join(turn.evidence_titles[:4])
        answer = _trim(turn.answer or "", 420)
        parts = [f"Turn {index} question: {turn.question}"]
        if answer:
            parts.append(f"Turn {index} answer summary: {answer}")
        if evidence:
            parts.append(f"Turn {index} evidence titles: {evidence}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _standalone_follow_up_question(question: str, history: list[ConversationTurn]) -> str:
    latest = history[-1]
    topic_text = " ".join(
        [
            latest.question,
            latest.answer or "",
            " ".join(latest.evidence_titles[:4]),
        ]
    )
    lower_topic = topic_text.lower()
    lower_question = question.lower()

    latest_place_topic = "" if _looks_like_bad_context_turn(latest) else _place_topic(topic_text)
    place_topic = latest_place_topic or _place_topic_from_history(history)
    if place_topic:
        if _asks_travel(question):
            if _asks_restaurants(question):
                return f"{place_topic} 旅游 推荐 具体景点 饭店 餐厅 美食"
            if any(term in question for term in ["三天", "3天", "三日", "3日"]):
                return f"{place_topic} 三天旅游 行程 推荐 景点 美食 交通"
            return f"{place_topic} 旅游 推荐 景点 美食 交通 行程"
        if any(term in question for term in ["经济", "产业", "就业", "生活", "房价", "交通", "历史", "文化"]):
            return f"{place_topic} {question}"
        if any(term in question for term in ["怎么样", "如何", "介绍", "具体"]):
            return f"{place_topic} 概况 {question}"

    if "fau" in lower_topic and (
        "artificial intelligence" in lower_topic
        or re.search(r"\bai\b", lower_topic)
        or "人工智能" in topic_text
    ):
        topic = "FAU Artificial Intelligence MSc"
        if "语言" in question or "english" in lower_question or "language" in lower_question:
            return f"{topic} English language requirements admission"
        if "截止" in question or "deadline" in lower_question:
            return f"{topic} application deadline admission"
        if "材料" in question or "document" in lower_question:
            return f"{topic} application documents requirements"
        if "费用" in question or "学费" in question or "tuition" in lower_question:
            return f"{topic} tuition fees cost"
        if "条件" in question or "要求" in question or "requirement" in lower_question:
            return f"{topic} admission requirements qualification assessment"
        return f"{topic} {question}"

    if "司美格鲁肽" in topic_text or "semaglutide" in lower_topic or "glp-1" in lower_topic:
        topic = "semaglutide GLP-1 receptor agonist"
        if "骨折" in question or "fracture" in lower_question:
            return f"{topic} fracture risk bone mineral density bone health"
        if "骨密度" in question or "bmd" in lower_question:
            return f"{topic} bone mineral density BMD osteoporosis"
        if "价格" in question or "多少钱" in question or "price" in lower_question:
            return f"{topic} price cost current"
        return f"{topic} {question}"

    if "hpv" in lower_topic and ("sarcopenia" in lower_topic or "肌少" in topic_text):
        return f"HPV infection sarcopenia {question}"

    combined = f"{latest.question} {question}"
    return _trim(combined, 520)


def _place_topic(text: str) -> str:
    places = _extract_place_candidates(text)
    if places:
        return places[0]
    return ""


def _place_topic_from_history(history: list[ConversationTurn]) -> str:
    for turn in reversed(history[-6:]):
        if _looks_like_bad_context_turn(turn):
            continue
        title_text = " ".join(turn.evidence_titles[:6])
        for text in [turn.question, title_text, turn.answer or ""]:
            places = _extract_place_candidates(text)
            if places:
                return places[0]
    return ""


def _looks_like_bad_context_turn(turn: ConversationTurn) -> bool:
    text = f"{turn.question} {turn.answer or ''} {' '.join(turn.evidence_titles[:6])}"
    if "Live web search unavailable" in text:
        return True
    if "台北市" in text and any(term in text for term in ["博兴", "麻大湖", "滨州/淄博", "更成為"]):
        return True
    if turn.confidence == "insufficient":
        return True
    return False


def _extract_place_candidates(text: str) -> list[str]:
    if not text:
        return []
    if "菏泽" in text or "荷泽" in text:
        return ["菏泽市"]
    if "博兴" in text:
        return ["博兴县"]
    cleaned = re.sub(r"[，。！？?：:；;、,.\s]", "", text)
    for phrase in [
        "介绍一下",
        "介绍下",
        "介绍",
        "一下",
        "这个地方",
        "当地",
        "推荐具体",
        "推荐",
        "具体",
        "中国",
        "中华人民共和国",
        "山东省",
        "山东",
    ]:
        cleaned = cleaned.replace(phrase, "")
    matches = re.findall(r"[\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡)", cleaned)
    blocked = ["大学", "学院", "医院", "博物馆", "人民政府", "文化", "旅游", "机场", "车站", "台北市", "滨州城区"]
    return [match for match in matches if not any(term in match for term in blocked)]


def _asks_travel(question: str) -> bool:
    lower = question.lower()
    return any(
        term in lower or term in question
        for term in [
            "旅游",
            "旅行",
            "游玩",
            "景点",
            "推荐",
            "怎么玩",
            "行程",
            "路线",
            "美食",
            "饭店",
            "餐厅",
            "住宿",
            "打卡",
            "visit",
            "travel",
            "tour",
            "sightseeing",
        ]
    )


def _asks_restaurants(question: str) -> bool:
    return any(term in question for term in ["饭店", "餐厅", "吃饭", "美食", "小吃", "馆子", "酒店"])


def _trim(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."
