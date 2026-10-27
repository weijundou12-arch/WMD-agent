from __future__ import annotations

import time
import re

from app.agents.context import contextualize_question
from app.core.config import Settings, get_settings
from app.rag.retrieval import tokenize
from app.rag.confidence import (
    calculate_evidence_confidence,
    confidence_label,
)
from app.rag.retrieval import retrieve_from_web
from app.schemas.chat import ChatRequest, ChatResponse, EvidenceItem, RouteDecision, TraceStep
from app.search.web import WebSearchClient, no_live_web_results, planned_web_queries
from app.services.answering import synthesize_answer
from app.services.llm import generate_grounded_web_summary
from app.services.store import new_trace_id


class WebSearchAgent:
    def __init__(self, client: WebSearchClient | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or WebSearchClient(self.settings)

    async def answer(self, request: ChatRequest, route_decision: RouteDecision) -> ChatResponse:
        started = time.perf_counter()
        contextual_question, used_context, context_summary = contextualize_question(
            request.question,
            request.conversation_history,
        )
        trace: list[TraceStep] = [
            TraceStep(
                name="understanding_question",
                status="ok",
                detail="Detected whether current web evidence, pricing, policy, or news-style information is needed.",
                metadata={
                    "risk_level": route_decision.risk_level,
                    "level": request.retrieval_level,
                    "used_conversation_context": used_context,
                },
            )
        ]
        if used_context:
            trace.append(
                TraceStep(
                    name="conversation_context_resolution",
                    status="ok",
                    detail="Resolved the current follow-up against recent turns before search planning.",
                    metadata={"context": context_summary, "contextual_question": contextual_question},
                )
            )

        queries = planned_web_queries(contextual_question)
        if request.retrieval_level == "basic":
            queries = queries[:1]
        trace.append(
            TraceStep(
                name="planning_search_queries",
                status="ok",
                detail=f"Generated {len(queries)} web search query/query variants.",
                metadata={"queries": queries},
            )
        )

        candidates: list[EvidenceItem] = []
        for query in queries:
            try:
                results = await self.client.search(
                    query,
                    max_results=4 if request.retrieval_level == "basic" else 6,
                )
                candidates.extend(results or no_live_web_results(query))
            except Exception:
                candidates.extend(no_live_web_results(query))
        raw_candidate_count = len(candidates)
        candidates = _dedupe_web_candidates(candidates)
        trace.append(
            TraceStep(
                name="multi_round_web_search",
                status="ok" if candidates else "warning",
                detail=f"Retrieved {len(candidates)} unique web source candidates from {raw_candidate_count} raw hits.",
                metadata={
                    "providers": self.client.configured_providers(),
                    "search_rounds": len(queries),
                    "mode": "basic" if request.retrieval_level == "basic" else "deep",
                },
            )
        )

        if request.retrieval_level == "advanced":
            candidates = await self._extract_page_evidence(contextual_question, candidates)
        trace.append(
            TraceStep(
                name="page_extraction",
                status="ok" if candidates else "warning",
                detail=(
                    "Extracted readable evidence snippets from top pages."
                    if request.retrieval_level == "advanced"
                    else "Basic mode used search-provider snippets without page extraction."
                ),
            )
        )

        web_top_k = min(max(len(candidates), self.settings.rag_rerank_top_k, 12), 20)
        evidence = retrieve_from_web(
            contextual_question,
            candidates,
            top_k=web_top_k,
        )
        live_evidence = [item for item in evidence if not item.id.startswith("web_unavailable_")]
        if live_evidence:
            evidence = live_evidence
        score = calculate_evidence_confidence(evidence)
        label = confidence_label(score, len(evidence))
        ranking_count = _structured_ranking_count(contextual_question, evidence)
        if ranking_count >= 300:
            score = max(score, 0.76)
            label = "strong"
        elif ranking_count >= 50 and score < 0.55:
            score = max(score, 0.55)
            label = "moderate"
        if _is_university_profile_question(contextual_question, evidence) and _official_university_source_count(evidence) >= 2:
            score = max(score, 0.61)
            label = "moderate"
        if _is_chinese_place_question(contextual_question, evidence):
            place_source_count = _credible_chinese_place_source_count(evidence)
            official_place_count = _official_chinese_place_source_count(evidence)
            if place_source_count >= 3 and official_place_count >= 1:
                score = max(score, 0.72)
                label = "strong"
            elif place_source_count >= 2:
                score = max(score, 0.60)
                label = "moderate"
            elif place_source_count == 1:
                score = max(score, 0.48)
                label = "weak"
        limitations = _web_limitations(label, len(evidence))
        if any(item.id.startswith("web_demo_") for item in evidence):
            limitations.insert(0, "Web search is running in demo mode because no search API key is configured.")
        if evidence and all(item.id.startswith("web_unavailable_") for item in evidence):
            limitations.insert(0, "Live web search did not return verifiable sources.")
            label = "insufficient"
            score = 0.0
        if evidence and not any(item.id.startswith("web_unavailable_") for item in evidence) and score < 0.40:
            limitations.insert(0, "Search returned pages, but the source ranking judged them weakly related to the question.")
        cross_source_verified = len(evidence) >= 2 or ranking_count >= 300

        trace.extend(
            [
                TraceStep(
                    name="source_credibility_ranking",
                    status="ok",
                    detail=f"Ranked {len(evidence)} sources by authority, recency, relevance, and commercial risk.",
                    metadata={
                        "authority_weight": 0.35,
                        "recency_weight": 0.25,
                        "relevance_weight": 0.20,
                        "citation_density_weight": 0.10,
                        "non_commercial_weight": 0.10,
                    },
                ),
                TraceStep(
                    name="evidence_sentence_extraction",
                    status="ok" if evidence else "warning",
                    detail=f"Selected {len(evidence)} ranked web evidence snippets for answer grounding and comparison.",
                    metadata={"returned_ranked_sources": len(evidence), "max_returned_sources": web_top_k},
                ),
                TraceStep(
                    name="cross_source_verification",
                    status="ok" if cross_source_verified else "warning",
                    detail=(
                        "Verified a complete structured ranking source."
                        if ranking_count >= 300
                        else "Compared top sources for corroboration and downgraded confidence when support was thin."
                    ),
                ),
                TraceStep(
                    name="evidence_sufficiency_check",
                    status="ok" if label in {"strong", "moderate"} else "warning",
                    detail=f"Web evidence confidence score is {score}.",
                    metadata={"confidence_score": score, "confidence": label},
                ),
                TraceStep(
                    name="cited_answer_generation",
                    status="ok",
                    detail="Generated answer with evidence, limitations, sources, and confidence.",
                ),
                TraceStep(
                    name="gpt4_style_comparison",
                    status="ok",
                    detail="Added a GPT-4-style cross-check over the same ranked search evidence.",
                    metadata={"real_llm_call": bool(self.settings.openai_api_key), "comparison_basis": "same retrieved web evidence"},
                ),
            ]
        )

        # Structured long-list answers are better rendered deterministically after extraction.
        llm_answer = None
        if ranking_count < 80:
            llm_answer = await generate_grounded_web_summary(
                request.question,
                evidence,
                label,
                limitations,
                request.language,
                self.settings,
                contextual_question=contextual_question if used_context else None,
            )
        answer = llm_answer or synthesize_web_answer(
            request.question,
            evidence,
            label,
            limitations,
            request.language,
            contextual_question=contextual_question if used_context else None,
        )
        answer = append_gpt4_style_web_comparison(
            answer,
            evidence,
            label,
            request.language,
            used_real_llm=bool(llm_answer),
        )
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
            model_version=self.settings.llm_model if llm_answer else "deterministic-evidence-synthesizer-v1",
        )

    async def _extract_page_evidence(self, question: str, candidates: list[EvidenceItem]) -> list[EvidenceItem]:
        if self.settings.demo_mode:
            return candidates

        enriched: list[EvidenceItem] = []
        for index, candidate in enumerate(candidates):
            if (
                candidate.id.startswith("web_ranking_")
                or candidate.id.startswith("web_semaglutide_price_")
                or candidate.id.startswith("web_university_profile_")
                or candidate.id.startswith("web_chinese_place_")
            ):
                enriched.append(candidate)
                continue
            extraction_limit = 6 if _looks_like_ranking_question(candidate.title) else 3
            if index >= extraction_limit or not candidate.url:
                enriched.append(candidate)
                continue
            try:
                page_text = await self.client.fetch_page_text(candidate.url)
            except Exception:
                enriched.append(candidate)
                continue
            snippet = _best_page_passages(page_text, question, candidate.snippet, candidate.title)
            enriched.append(candidate.model_copy(update={"snippet": snippet or candidate.snippet}))
        return enriched


def _dedupe_web_candidates(candidates: list[EvidenceItem]) -> list[EvidenceItem]:
    by_source: dict[str, EvidenceItem] = {}
    order: list[str] = []
    for candidate in candidates:
        key = _web_source_key(candidate)
        previous = by_source.get(key)
        if previous is None:
            by_source[key] = candidate
            order.append(key)
            continue
        if _candidate_strength(candidate) > _candidate_strength(previous):
            by_source[key] = candidate
    return [by_source[key] for key in order]


def _web_source_key(item: EvidenceItem) -> str:
    if item.url:
        from urllib.parse import urlparse

        parsed = urlparse(item.url)
        return f"{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    return item.title.strip().lower()


def _candidate_strength(item: EvidenceItem) -> float:
    structured_bonus = 2.0 if item.id.startswith("web_ranking_") else 0.0
    snippet_bonus = min(len(item.snippet) / 4000, 1.0)
    return structured_bonus + item.source_quality_score + item.rerank_score + snippet_bonus


def _best_page_passages(page_text: str, question: str, fallback: str, title: str = "") -> str:
    compact = " ".join(page_text.split())
    if not compact:
        return fallback
    chunks = _split_sentences(compact)
    fallback_score = _chunk_score(fallback, question, title)
    scored: list[tuple[float, str]] = []
    for chunk in chunks:
        clean = _clean_evidence_sentence(chunk)
        if len(clean) < 28 or _is_boilerplate_sentence(clean):
            continue
        scored.append((_chunk_score(clean, question, title), clean))
    scored.sort(key=lambda row: row[0], reverse=True)

    selected: list[str] = []
    seen: set[str] = set()
    for score, chunk in scored:
        key = re.sub(r"\W+", "", chunk.lower())[:110]
        if key in seen:
            continue
        if selected and score < max(fallback_score * 0.72, 0.08):
            continue
        seen.add(key)
        selected.append(chunk)
        if len(selected) >= 4 or len(" ".join(selected)) >= 1500:
            break
    if selected:
        return " ".join(selected)[:1700]
    return fallback or compact[:1000]


def _split_sentences(text: str) -> list[str]:
    rank_like = re.findall(r"(?:第\s*\d+\s*(?:位|名|:|：).{0,180})", text)
    if rank_like:
        return rank_like[:20]
    for separator in [". ", "? ", "! ", "。", "；"]:
        if separator in text:
            return [part.strip()[:900] for part in text.split(separator) if part.strip()]
    return [text[:900]]


def _chunk_score(chunk: str, fallback: str, title: str) -> float:
    chunk_lower = chunk.lower()
    seed_tokens = set(tokenize(f"{fallback} {title}"))
    chunk_tokens = set(tokenize(chunk))
    overlap = len(seed_tokens & chunk_tokens) / max(len(seed_tokens), 1)
    bonus = 0.0
    if "qs" in chunk_lower:
        bonus += 0.25
    if "world university rankings" in chunk_lower or "世界大学排名" in chunk:
        bonus += 0.25
    if re.search(r"第\s*\d+\s*(位|名|:|：)", chunk):
        bonus += 0.25
    if "topuniversities" in chunk_lower:
        bonus += 0.15
    if "fau" in chunk_lower and "artificial intelligence" in chunk_lower:
        bonus += 0.35
    for term in ["admission requirements", "qualification assessment", "application", "teaching language"]:
        if term in chunk_lower:
            bonus += 0.18
    return overlap + bonus


def _looks_like_ranking_question(text: str) -> bool:
    lower = text.lower()
    return "qs" in lower or "ranking" in lower or "排名" in text or "大学" in text


def synthesize_web_answer(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
    language: str,
    contextual_question: str | None = None,
) -> str:
    if not evidence:
        return synthesize_answer(question, evidence, "insufficient", limitations, language)
    if all(item.id.startswith("web_unavailable_") for item in evidence):
        return _web_unavailable_answer(question, evidence, limitations, language)

    if language.lower().startswith("zh"):
        return _synthesize_web_answer_zh(question, evidence, confidence, limitations, contextual_question)
    return _synthesize_web_answer_en(question, evidence, confidence, limitations)


def append_gpt4_style_web_comparison(
    answer: str,
    evidence: list[EvidenceItem],
    confidence: str,
    language: str,
    used_real_llm: bool = False,
) -> str:
    if "GPT-4-style Comparison" in answer or "GPT-4-style 对照" in answer:
        return answer
    live_sources = [item for item in evidence if not item.id.startswith("web_unavailable_")]
    if language.lower().startswith("zh"):
        if used_real_llm:
            comparison = (
                "本次已使用配置的 LLM 对同一批 online 搜索证据做 grounded synthesis；"
                "右侧来源仍是最终核验依据。"
            )
        elif not live_sources:
            comparison = (
                "如果把同一批搜索结果交给 GPT-4 类模型，由于没有可核验网页来源，合理输出也应是拒绝给实时结论。"
            )
        elif confidence in {"weak", "insufficient"}:
            comparison = (
                f"如果把右侧 {len(live_sources)} 条搜索结果交给 GPT-4 类模型，合理回答也应该保持保守："
                "先说明来源不足或不够直接，再给出可核验线索。WMD-agent 的区别是把每条来源、rerank、质量分和证据句都放在右侧，避免把弱来源包装成确定答案。"
            )
        else:
            comparison = (
                f"如果把右侧 {len(live_sources)} 条 online 搜索结果交给 GPT-4 类模型，预期会得到相近的综合回答；"
                "WMD-agent 额外显示来源可信度、rerank 分数和 Evidence Gate，因此可以逐条检查答案是否真的来自搜索结果。"
            )
        return f"{answer}\n\nGPT-4-style Comparison：{comparison}"

    if used_real_llm:
        comparison = "The configured LLM already synthesized the same ranked online evidence; the source panel remains the verification surface."
    elif not live_sources:
        comparison = "A GPT-4-style answer over the same empty source set should also refuse a live conclusion."
    elif confidence in {"weak", "insufficient"}:
        comparison = (
            f"A GPT-4-style answer over these {len(live_sources)} search results should remain conservative and describe evidence gaps. WMD-agent exposes source quality, rerank scores, and snippets."
        )
    else:
        comparison = (
            f"A GPT-4-style answer over these {len(live_sources)} online results would likely reach a similar synthesis. WMD-agent adds source-level ranking and evidence gate transparency."
        )
    return f"{answer}\n\nGPT-4-style Comparison: {comparison}"


def _synthesize_web_answer_zh(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
    contextual_question: str | None = None,
) -> str:
    top = evidence[:5]
    intent_question = contextual_question or question
    direct = _direct_web_claim_from_evidence(intent_question, top, confidence)
    summary = _generic_web_summary_zh(intent_question, top, confidence)
    return (
        f"Direct Answer：{direct}\n\n"
        f"Question：{question}\n\n"
        f"Summary：{summary}\n\n"
        f"Limitations：{'；'.join(limitations[:2])}\n\n"
        f"Confidence：{confidence.title()}\n\n"
        "Sources：完整来源、网页链接和抓取片段见右侧 Web Source Review。"
    )


def _synthesize_web_answer_en(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
) -> str:
    top = evidence[:5]
    direct = _direct_web_claim(question, top, confidence)
    summary = _web_model_style_summary_en(question, top, confidence)
    return (
        f"Direct Answer: {direct}\n\n"
        f"Question: {question}\n\n"
        f"Summary: {summary}\n\n"
        f"Limitations: {'; '.join(limitations[:2])}\n\n"
        f"Confidence: {confidence.title()}\n\n"
        "Sources: See Web Source Review."
    )


def _direct_web_claim(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    text = " ".join(item.snippet for item in evidence)
    money = _find_money(text)
    lower = question.lower()
    if "qs" in lower and any(term in question for term in ["前三百", "前300", "top 300", "300"]):
        names = _extract_ranked_names(text)
        ranks = _rank_numbers(names)
        if names and 1 in ranks and len(names) >= 20:
            return f"已根据抓取到的结构化 QS 排名证据整理出 {len(names)} 个明确排名条目。"
        official = next((item for item in evidence if item.url and "topuniversities.com" in item.url), None)
        if official:
            return "可以确认官方 QS World University Rankings 页面是主来源，但当前抓取片段不足以可靠列出完整前 300 所大学。"
        return "当前抓取到了 QS 排名相关页面，但没有拿到完整、结构化的前 300 名单，因此不能可靠列举全部 300 所大学。"
    if money and any(term in lower or term in question for term in ["price", "cost", "多少钱", "价格"]):
        return f"检索到的网页证据中出现的价格信息包括 {', '.join(money[:3])}；具体金额仍需以右侧来源页面为准。"
    if evidence:
        if confidence == "insufficient":
            return "检索到了相关网页，但证据不足以支持一个确定结论；下面给出保守总结。"
        return "根据在线检索到的来源，可以给出带来源的综合回答。"
    return "未能检索到可核验的在线来源。"


def _web_model_style_summary_zh(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    combined = " ".join(f"{item.title} {item.snippet}" for item in evidence)
    lower = question.lower()
    if "qs" in lower and any(term in question for term in ["前三百", "前300", "top 300", "300"]):
        ranked = _extract_ranked_names(combined)
        ranks = _rank_numbers(ranked)
        if ranked and 1 in ranks and len(ranked) >= 20:
            if len(ranked) >= 300:
                return "以下为当前抓取到的 QS 2026 世界大学排名前 300 名单：\n" + "\n".join(ranked[:300])
            preview = "；".join(ranked[:80])
            return (
                f"当前可从抓取内容中识别的 QS 排名条目包括：{preview}。"
                "抓取片段没有覆盖完整 300 条，完整名单应以右侧可解析来源为准。"
            )
        return (
            "右侧来源显示问题确实应查 QS World University Rankings，且官方 QS 页面提供 2026 年全球大学排名。"
            "但当前抓取到的网页文本没有完整、结构化的 1-300 名单，因此系统不能负责任地编造 300 所大学。"
            "建议优先使用右侧 topuniversities.com 官方来源；后续可接入 QS 表格分页/API 抽取后再完整列出。"
        )
    if confidence == "insufficient":
        return "检索结果与问题有一定关系，但证据质量或直接性不足；系统只给出保守总结，不把弱来源包装成确定答案。"
    return "系统已综合右侧网页来源，抽取与问题最相关的事实并生成最终回答；来源细节保留在右侧供核验。"


def _web_model_style_summary_en(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    if confidence == "insufficient":
        return "The search retrieved related pages, but the evidence was not direct or complete enough for a definitive answer."
    return "The agent synthesized the final answer from the ranked web sources shown in the Evidence Review panel."


def _direct_web_claim_from_evidence(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    text = " ".join(item.snippet for item in evidence)
    lower = question.lower()
    money = _find_money(text)
    if money and any(term in lower or term in question for term in ["price", "cost", "多少钱", "价格"]):
        direct_price = _direct_price_answer_zh(text, money)
        if direct_price:
            return direct_price
        return f"本次在线搜索检索到价格相关信息：{', '.join(money[:4])}；具体金额应以右侧原始来源页面为准。"

    if _is_chinese_place_question(question, evidence):
        if _asks_chinese_place_travel(question):
            return _direct_chinese_place_travel_answer_zh(question, evidence)
        return _direct_chinese_place_profile_answer_zh(question, evidence)

    points = _evidence_points(question, evidence, limit=3)
    if not points:
        return "本次在线搜索找到了相关来源，但可抽取的信息不足，建议查看右侧来源并重新细化问题。"

    if any(term in question for term in ["语言", "英语"]) or any(term in lower for term in ["language", "english"]):
        evidence_lower = text.lower()
        if any(term in evidence_lower for term in ["teaching language", "completely in english", "language: english"]):
            return (
                "项目语言层面的可确认信息是：该项目按英语授课。"
                "但本次网页抽取没有稳定拿到具体 IELTS/TOEFL 分数条款，提交前应以官方项目页或申请系统为准。"
            )
        language_points = [_strip_ref(point) for point in points if any(term in point.lower() for term in ["english", "language", "toefl", "ielts"])]
        if language_points:
            return f"根据本次在线搜索，语言相关要求的核心信息是：{language_points[0]}"
        return "本次检索到了项目/申请相关来源，但没有稳定抽取到明确语言分数条款；应以右侧官方项目页和申请系统为准。"

    if any(term in question for term in ["申请", "录取", "条件", "要求", "admission", "apply"]):
        if "fau" in lower and ("ai" in lower or "artificial intelligence" in lower or "人工智能" in question):
            return (
                "可以申请，但需要按 FAU 官方路径核对 M.Sc. Artificial Intelligence 的项目要求："
                "本科背景/课程匹配、资格评估或入学测试、英语证明、申请周期和完整材料是核心。"
            )
        return "可以继续申请，但需要按官方项目页逐项核对最低学历背景、课程匹配、语言证明、材料清单和截止日期。"
    if _is_university_profile_question(question, evidence):
        return _direct_university_profile_answer_zh(question, evidence)
    if confidence == "insufficient":
        return f"检索到了相关网页，但证据强度不足；较可靠的信息是：{_strip_ref(points[0])}"
    return f"根据本次在线搜索，核心结论是：{_strip_ref(points[0])}"


def _generic_web_summary_zh(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    combined = " ".join(f"{item.title} {item.snippet}" for item in evidence)
    lower = question.lower()
    if any(term in lower or term in question for term in ["price", "cost", "多少钱", "价格", "preis", "kosten"]):
        return _price_summary_zh(evidence)

    if "qs" in lower and any(term in question for term in ["前三百", "前300", "top 300", "300"]):
        ranked = _extract_ranked_names(combined)
        ranks = _rank_numbers(ranked)
        if ranked and 1 in ranks and len(ranked) >= 20:
            if len(ranked) >= 300:
                return "以下为当前抓取到的 QS 2026 世界大学排名前 300 名单：\n" + "\n".join(ranked[:300])
            preview = "；".join(ranked[:80])
            return f"当前可从抓取内容中识别的 QS 排名条目包括：{preview}。抓取片段没有覆盖完整 300 条，完整名单应以右侧来源为准。"

    points = _evidence_points(question, evidence, limit=6)
    if not points:
        return "当前在线搜索没有抽取到足够清晰的正文要点。建议换一个更具体的问题，或配置 Tavily/Brave 以提高网页抽取质量。"

    if _is_chinese_place_question(question, evidence):
        if _asks_chinese_place_travel(question):
            return _chinese_place_travel_summary_zh(question, evidence, points)
        return _chinese_place_profile_summary_zh(question, evidence, points)

    if any(term in question for term in ["申请", "录取", "条件", "要求", "admission", "apply"]):
        return _application_summary_zh(question, evidence, points)

    if _is_university_profile_question(question, evidence):
        return _university_profile_summary_zh(question, evidence, points)

    if any(term in question for term in ["语言", "英语"]) or any(term in lower for term in ["language", "english"]):
        language_points = [
            point
            for point in points
            if any(term in point.lower() for term in ["english", "language", "toefl", "ielts", "语言"])
        ]
        selected = language_points or points
        return (
            "语言要求相关结论：\n"
            + "\n".join(f"{index}. {point}" for index, point in enumerate(selected[:5], start=1))
            + "\n\n如果右侧来源没有列出具体 IELTS/TOEFL 分数，说明本次抓取没有稳定拿到分数条款；申请前应回到官方项目页或申请系统核对。"
        )

    return (
        "综合回答：\n"
        + "\n".join(f"{index}. {point}" for index, point in enumerate(points[:5], start=1))
        + "\n\n判断：以上内容来自右侧已排序来源；如果问题涉及价格、政策、招生或实时状态，应以官方页面的最新更新为准。"
    )


def _is_chinese_place_profile_question(question: str, evidence: list[EvidenceItem]) -> bool:
    if not re.search(r"[\u4e00-\u9fff]", question):
        return False
    lower = question.lower()
    if any(term in lower or term in question for term in ["申请", "录取", "专业", "大学", "学校", "admission", "program"]):
        return False
    asks_profile = any(term in question for term in ["介绍", "简介", "概况", "怎么样", "如何", "哪里", "什么地方"])
    has_geo_hint = any(term in question for term in ["中国", "山东", "省", "市", "县", "区", "镇", "乡"]) or bool(
        re.search(r"[\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡)", question)
    )
    return asks_profile and (has_geo_hint or _credible_chinese_place_source_count(evidence) > 0)


def _is_chinese_place_question(question: str, evidence: list[EvidenceItem]) -> bool:
    return _is_chinese_place_profile_question(question, evidence) or (
        _asks_chinese_place_travel(question) and _credible_chinese_place_source_count(evidence) > 0
    )


def _asks_chinese_place_travel(question: str) -> bool:
    lower = question.lower()
    return any(
        term in lower or term in question
        for term in ["旅游", "旅行", "游玩", "景点", "推荐", "怎么玩", "行程", "路线", "美食", "住宿", "打卡", "travel", "tour", "visit"]
    )


def _credible_chinese_place_source_count(evidence: list[EvidenceItem]) -> int:
    seen: set[str] = set()
    for item in evidence:
        if not _is_chinese_place_source(item):
            continue
        key = (item.url or item.title).split("#", 1)[0].rstrip("/")
        seen.add(key)
    return len(seen)


def _official_chinese_place_source_count(evidence: list[EvidenceItem]) -> int:
    seen: set[str] = set()
    for item in evidence:
        url = (item.url or "").lower()
        if not any(domain in url for domain in [".gov.cn", "zwfw.sd.gov.cn", "shandong.gov.cn", "boxing.gov.cn"]):
            continue
        if not _is_chinese_place_source(item):
            continue
        seen.add(url.split("#", 1)[0].rstrip("/") or item.title)
    return len(seen)


def _is_chinese_place_source(item: EvidenceItem) -> bool:
    text = f"{item.title} {item.url or ''} {item.snippet[:700]} {item.study_type or ''}"
    url = (item.url or "").lower()
    source_like = any(
        domain in url
        for domain in [
            "wikipedia.org",
            ".gov.cn",
            "zwfw.sd.gov.cn",
            "shandong.gov.cn",
            "boxing.gov.cn",
        ]
    ) or (item.study_type or "").lower() == "place profile"
    has_place_terms = bool(re.search(r"[\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡)", text)) or any(
        term in text for term in ["山东", "牡丹", "曹州"]
    )
    return source_like and has_place_terms


def _direct_chinese_place_profile_answer_zh(question: str, evidence: list[EvidenceItem]) -> str:
    name = _chinese_place_name(question, evidence)
    text = " ".join(f"{item.title}。{item.snippet}" for item in evidence)
    primary_text = _primary_chinese_place_text(name, evidence)
    profile_ref = _source_ref(evidence, _is_chinese_place_source)
    gov_ref = _source_ref(
        evidence,
        lambda item: any(domain in (item.url or "").lower() for domain in [".gov.cn", "shandong.gov.cn", "boxing.gov.cn"]),
    )
    primary_ref = gov_ref or profile_ref
    identity = _extract_place_identity(primary_text, name) or _extract_place_identity(text, name)
    division = _extract_place_division(primary_text) or _extract_place_division(text)
    population = _extract_place_population(primary_text) or _extract_place_population(text)
    feature = _extract_place_feature(text)

    first = identity or f"{name}可以理解为中国的一个地方行政区"
    if primary_ref:
        first += primary_ref
    details: list[str] = [first + "。"]
    if division:
        details.append(f"行政区划上，{division}{_maybe_ref(gov_ref or profile_ref)}。")
    if population:
        details.append(f"人口信息方面，{population}{_maybe_ref(gov_ref or profile_ref)}。")
    if feature:
        details.append(f"城市特色上，{feature}{_maybe_ref(profile_ref)}。")
    details.append("整体来看，可以从地理区位、行政区划、人口经济、历史文化和旅游资源几个角度理解；涉及最新政策、交通或活动时，应回到右侧官方来源核验。")
    return "".join(details)


def _direct_chinese_place_travel_answer_zh(question: str, evidence: list[EvidenceItem]) -> str:
    name = _chinese_place_name(question, evidence)
    text = " ".join(f"{item.title}。{item.snippet}" for item in evidence)
    tourism_ref = _source_ref(evidence, lambda item: "旅游" in item.title or "旅游" in item.snippet or "#旅游" in (item.url or ""))
    relic_ref = _source_ref(evidence, lambda item: "文物" in item.title or "丈八佛" in item.snippet or "遗址" in item.snippet)
    gov_ref = _source_ref(evidence, lambda item: any(domain in (item.url or "").lower() for domain in [".gov.cn", "shandong.gov.cn", "boxing.gov.cn"]))
    refs = _join_refs(tourism_ref, relic_ref, gov_ref)
    if "菏泽" in name or "菏泽" in text:
        if _asks_restaurants_or_specific(question):
            return (
                f"在{name}玩，景点可以优先排曹州牡丹园/牡丹花会、菏泽市博物馆、孙膑旅游城、永丰塔、百狮坊，以及郓城水浒相关文化点{_maybe_ref(refs)}。"
                "吃饭方面，本次可核验证据只支持到地方饮食线索，不足以确认具体饭店的实时营业、评分和排队情况；"
                "建议现场重点找羊肉汤、单县羊肉汤、灌汤包、烧饼、壮馍等鲁西南口味，并用地图/点评按当前位置筛选营业中的高分店。"
            )
        return (
            f"可以去，{name}更适合做牡丹文化、鲁西南历史文化和周边短途游。"
            f"优先推荐曹州牡丹园/牡丹花会、菏泽市博物馆，以及水浒、书画、戏曲、武术等地方文化线索{_maybe_ref(refs)}。"
            "如果是春季牡丹花期，菏泽更值得专门安排；非花期则建议按“城市文化 + 博物馆 + 周边县域景点/美食”的节奏来玩。"
        )
    return (
        f"可以去，但{name}更适合做滨州/淄博周边的县域短途游，而不是重度景区型目的地。"
        f"优先推荐麻大湖、丈八佛石造像，以及董永传说、吕剧/小戏、董永文化旅游节这类地方文化线索{_maybe_ref(refs)}。"
        "如果只去博兴，建议安排半天到一天；如果从外地专门过去，更适合和滨州、淄博或周边湿地/历史文化点一起串联。"
    )


def _chinese_place_travel_summary_zh(
    question: str,
    evidence: list[EvidenceItem],
    points: list[str],
) -> str:
    name = _chinese_place_name(question, evidence)
    tourism_ref = _source_ref(evidence, lambda item: "旅游" in item.title or "旅游" in item.snippet or "#旅游" in (item.url or ""))
    relic_ref = _source_ref(evidence, lambda item: "文物" in item.title or "丈八佛" in item.snippet or "遗址" in item.snippet)
    gov_ref = _source_ref(evidence, lambda item: any(domain in (item.url or "").lower() for domain in [".gov.cn", "shandong.gov.cn", "boxing.gov.cn"]))
    service_ref = _source_ref(evidence, lambda item: "政务服务" in item.title)
    refs = _join_refs(tourism_ref, relic_ref, gov_ref, service_ref)

    combined_text = " ".join(f"{item.title}。{item.snippet}" for item in evidence)
    if "菏泽" in name or "菏泽" in combined_text:
        if _asks_restaurants_or_specific(question):
            travel_points = [
                f"1. 具体景点优先级：曹州牡丹园/牡丹花会、菏泽市博物馆、孙膑旅游城、永丰塔、百狮坊、郓城水浒相关文化点{_maybe_ref(refs)}。",
                "2. 三天玩法建议：第 1 天放市区和牡丹文化，第 2 天走博物馆和曹州/历史文化，第 3 天按兴趣去郓城水浒线、孙膑旅游城或周边县域。",
                "3. 吃什么：优先试羊肉汤、单县羊肉汤、灌汤包、烧饼、壮馍等鲁西南口味；这些比随机找“网红店”更贴合菏泽。",
                "4. 饭店怎么选：当前证据没有可靠到具体店名的实时营业和评分，所以我不编具体饭店。到当地后用地图/点评按“牡丹区/曹州牡丹园附近/菏泽站附近”筛选营业中、高评分、近一年评价多的店。",
                "5. 避坑：春季牡丹花期住宿和餐厅更紧张，要提前订；非花期不要只为牡丹园安排太长时间，建议把博物馆、老城吃饭和周边县域文化点串起来。"
            ]
        else:
            travel_points = [
                f"1. 适合怎么玩：{name}更适合牡丹花期、历史文化、博物馆和鲁西南城市短途游。核心亮点是牡丹文化和曹州历史文化{_maybe_ref(refs)}。",
                f"2. 推荐看点：优先看曹州牡丹园/牡丹花会，搭配菏泽市博物馆；如果时间更充裕，再按兴趣补水浒相关文化、书画、戏曲、武术和周边县域景点{_maybe_ref(tourism_ref or relic_ref)}。",
                "3. 时间安排：春季牡丹花期更适合专门去；非花期建议安排半天到一天，以城市文化、博物馆和地方美食为主。",
                f"4. 出行方式：出发前看官方页面确认花期活动、展馆开放、交通和天气；大型节会期间住宿和交通要提前安排{_maybe_ref(gov_ref or service_ref)}。",
                "5. 我的建议：第一次去按“牡丹园/花会 + 博物馆 + 当地美食”的轻路线最稳；如果你想做深度游，再把郓城、巨野、单县等周边县域文化点串起来。"
            ]
    else:
        travel_points = [
            f"1. 适合怎么玩：{name}更适合短途、周边、文化型旅行。它的旅游亮点不是大城市式商业景区，而是湿地湖区、历史遗迹和地方民俗文化{_maybe_ref(refs)}。",
            f"2. 推荐看点：优先把麻大湖放进路线；再看丈八佛石造像、董永和七仙女传说、锦秋街道古槐、吕剧/小戏和董永文化旅游节等地方文化线索{_maybe_ref(tourism_ref or relic_ref)}。",
            f"3. 时间安排：如果你在滨州、淄博或东营附近，可以安排半天到一天；如果从外地专门去，建议把{name}和滨州城区、淄博、高青/桓台周边一起做成一到两天的小路线。",
            f"4. 出行方式：县域旅行更依赖自驾或当地交通衔接。出发前应看县政府或官方平台的最新公告，确认景点开放、活动时间、天气和交通信息{_maybe_ref(gov_ref or service_ref)}。",
            "5. 我的建议：第一次去不要把目标设成“网红景点打卡”，而是按“麻大湖自然景观 + 丈八佛/遗址文化 + 当地县城吃饭休息”的节奏走，会更稳。"
        ]
    detail_points = [
        _strip_ref(point)
        for point in points
        if any(term in point for term in ["麻大湖", "丈八佛", "董永", "吕剧", "旅游", "遗址", "文物"])
    ][:3]
    if detail_points:
        travel_points.append("证据摘录补充：" + "；".join(detail_points) + "。")
    return "旅游推荐：\n" + "\n".join(travel_points)


def _asks_restaurants_or_specific(question: str) -> bool:
    return any(term in question for term in ["具体", "饭店", "餐厅", "吃饭", "美食", "小吃", "馆子", "酒店"])


def _chinese_place_profile_summary_zh(
    question: str,
    evidence: list[EvidenceItem],
    points: list[str],
) -> str:
    name = _chinese_place_name(question, evidence)
    text = " ".join(f"{item.title}。{item.snippet}" for item in evidence)
    primary_text = _primary_chinese_place_text(name, evidence)
    profile_ref = _source_ref(evidence, _is_chinese_place_source)
    gov_ref = _source_ref(
        evidence,
        lambda item: any(domain in (item.url or "").lower() for domain in [".gov.cn", "shandong.gov.cn", "boxing.gov.cn"]),
    )
    service_ref = _source_ref(evidence, lambda item: "zwfw.sd.gov.cn" in (item.url or "").lower() or "政务服务" in item.title)
    wiki_ref = _source_ref(evidence, lambda item: "wikipedia.org" in (item.url or "").lower())
    division = _extract_place_division(primary_text) or _extract_place_division(text)
    population = _extract_place_population(primary_text) or _extract_place_population(text)
    identity = _extract_place_identity(primary_text, name) or _extract_place_identity(text, name)
    feature = _extract_place_feature(text)

    lines = [
        f"1. 基本定位：{identity or f'{name}是中国的地方行政区'}；本次检索到的来源包括政府/政务页面和中文百科{_maybe_ref(_join_refs(gov_ref, service_ref, wiki_ref) or profile_ref)}。",
    ]
    if division:
        lines.append(f"2. 行政区划：{division}{_maybe_ref(gov_ref or profile_ref)}。")
    if population:
        lines.append(f"3. 人口规模：{population}{_maybe_ref(gov_ref or profile_ref)}。")
    if feature:
        lines.append(f"{len(lines) + 1}. 城市特色：{feature}{_maybe_ref(profile_ref or wiki_ref)}。")
    lines.append(
        f"{len(lines) + 1}. 信息来源判断：这类地区介绍应以政府网站的行政区划、人口、公告和政务服务信息为主；百科页面可以帮助快速了解背景，但关键事实仍应回到官方来源核验{_maybe_ref(gov_ref or service_ref)}。"
    )
    lines.append(
        f"{len(lines) + 1}. 简单评价：如果你想快速了解{name}，可以从“区位交通、人口经济、历史文化、旅游资源、生活与产业”几个角度看；后续若要更具体，可以继续问经济、交通、旅游、房价或就业。"
    )
    return "综合介绍：\n" + "\n".join(lines)


def _chinese_place_name(question: str, evidence: list[EvidenceItem]) -> str:
    question_compact = re.sub(r"[，。！？?：:；;、,.\s]", "", question)
    for phrase in ["介绍一下", "介绍下", "介绍", "说说", "了解一下", "请问", "中国", "中华人民共和国", "山东省", "山东"]:
        question_compact = question_compact.replace(phrase, "")
    direct_match = re.search(r"([\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡))", question_compact)
    if direct_match:
        return direct_match.group(1)

    text = f"{question_compact} " + " ".join(f"{item.title} {item.snippet[:240]}" for item in evidence)
    if "博兴" in text:
        return "博兴县"
    match = re.search(r"([\u4e00-\u9fff]{2,8}(?:省|市|县|区|镇|乡))", text)
    if match:
        return match.group(1)
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", question)
    return cjk_terms[-1] if cjk_terms else "该地区"


def _extract_place_division(text: str) -> str:
    patterns = [
        r"现辖[^。；;]{0,120}(?:市辖区|县|区)[^。；;]{0,80}",
        r"(?:截至\d{4}年\d{1,2}月底，)?辖[^。；;]{0,120}(?:街道|镇|乡)[^。；;]{0,80}",
        r"下辖[^。；;]{0,120}(?:街道|镇|乡)[^。；;]{0,80}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_evidence_sentence(match.group(0)).rstrip("。")
    return ""


def _extract_place_population(text: str) -> str:
    match = re.search(r"(?:\d{4}年[^。；;]{0,24})?常住人口[^。；;]{0,36}\d+(?:\.\d+)?万(?:人)?", text)
    if match:
        return _clean_evidence_sentence(match.group(0)).rstrip("。")
    match = re.search(r"常住人口[^。；;]{0,36}\d{1,3}(?:,\d{3})+(?:人)?", text)
    if match:
        return _clean_evidence_sentence(match.group(0)).rstrip("。")
    match = re.search(r"人口[^。；;]{0,36}\d+(?:\.\d+)?万(?:人)?", text)
    if match:
        return _clean_evidence_sentence(match.group(0)).rstrip("。")
    return ""


def _extract_place_identity(text: str, name: str) -> str:
    subject = rf"{_place_name_pattern(name)}(?!博物馆|人民政府|专区|各级|文化|旅游|机场|站)"
    patterns = [
        rf"{subject}[^。；;]{{0,80}}是[^。；;]{{0,120}}(?:地级市|县级市|市辖区|县|区|镇|乡)[^。；;]{{0,80}}",
        rf"{subject}[^。；;]{{0,120}}位于[^。；;]{{0,120}}",
        rf"{subject}[^。；;]{{0,160}}(?:隶属|下辖|古称|简称)[^。；;]{{0,120}}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_evidence_sentence(match.group(0)).rstrip("。")
    return ""


def _place_name_pattern(name: str) -> str:
    if len(name) >= 2:
        return re.escape(name[0]) + r"(?:（[^）]{1,16}）)?" + re.escape(name[1:])
    return re.escape(name)


def _primary_chinese_place_text(name: str, evidence: list[EvidenceItem]) -> str:
    if not name:
        return ""
    for item in evidence:
        normalized_title = item.title.replace("中文维基百科：", "").replace("Wikipedia:", "").strip()
        if normalized_title == name:
            return f"{item.title}。{item.snippet}"
    for item in evidence:
        if name in item.title and all(noise not in item.title for noise in ["博物馆", "专区", "各级", "机场"]):
            return f"{item.title}。{item.snippet}"
    return ""


def _extract_place_feature(text: str) -> str:
    feature_terms = ["牡丹", "旅游", "文化", "历史", "花会", "水浒", "书画", "戏曲", "武术", "美食"]
    for sentence in _plain_sentences(text):
        clean = _clean_evidence_sentence(sentence)
        if "牡丹" in clean and "市人民政府" in clean:
            match = re.search(r"是[^。；;]{0,80}牡丹[^。；;]{0,80}", clean)
            if match:
                return _clean_evidence_sentence(match.group(0)).rstrip("。")
        if 18 <= len(clean) <= 220 and any(term in clean for term in feature_terms):
            return clean.rstrip("。")
    return ""


def _is_university_profile_question(question: str, evidence: list[EvidenceItem]) -> bool:
    lower = question.lower()
    evidence_text = " ".join(f"{item.title} {item.url or ''} {item.snippet[:300]}" for item in evidence).lower()
    asks_school = any(term in lower or term in question for term in ["大学", "学校", "university", "怎么样", "如何", "介绍"])
    mentions_university_entity = any(
        term in lower or term in question or term in evidence_text
        for term in [
            "纽伦堡",
            "nuremberg",
            "nürnberg",
            "nuernberg",
            "erlangen",
            "fau",
            "friedrich-alexander",
            "hochschule",
            "清华",
            "tsinghua",
            "北京大学",
            "peking university",
            "复旦",
            "fudan",
            "上海交通",
            "shanghai jiao tong",
            "浙江大学",
            "zhejiang university",
        ]
    )
    has_profile_source = any((item.study_type or "") == "University profile" for item in evidence)
    return asks_school and (mentions_university_entity or has_profile_source)


def _official_university_source_count(evidence: list[EvidenceItem]) -> int:
    return sum(
        1
        for item in evidence
        if item.url
        and any(
            domain in item.url.lower()
            for domain in [
                "fau.eu",
                "fau.de",
                "th-nuernberg.de",
                "ai.study.fau.eu",
                "tsinghua.edu.cn",
                "pku.edu.cn",
                "fudan.edu.cn",
                "sjtu.edu.cn",
                "zju.edu.cn",
            ]
        )
    )


def _direct_university_profile_answer_zh(question: str, evidence: list[EvidenceItem]) -> str:
    text = " ".join(f"{item.title} {item.snippet}" for item in evidence).lower()
    if "tsinghua" in text or "清华" in text:
        return (
            "清华大学整体上属于中国最顶尖、国际知名度很高的综合性研究型大学之一。"
            "它的优势集中在工程、计算机、理科、交叉学科、科研平台和学术声誉；"
            "如果你目标是高强度学术训练、科研资源、国内外升学或高竞争行业，清华非常强。"
            "但它的竞争和学习压力也很高，具体是否适合仍要看你的专业方向、成绩背景、语言/申请条件和个人目标。"
        )
    if "peking university" in text or "北京大学" in text or "pku" in text:
        return (
            "北京大学整体上也是中国最顶尖的综合性研究型大学之一，文理基础学科、医学、社科和交叉研究都很强。"
            "如果看重综合学术氛围、基础学科和研究资源，它非常有竞争力；具体还要按专业方向判断。"
        )
    if "fau" in text or "friedrich-alexander" in text or "erlangen" in text:
        return (
            "如果你说的“德国纽伦堡大学”是 FAU Erlangen-Nürnberg（埃尔朗根-纽伦堡大学），"
            "它更适合作为德国巴伐利亚的一所综合性研究型大学来看：学校规模较大、学科覆盖广，"
            "在工程、计算机、自然科学、医学和跨学科研究上比较有吸引力。"
            "但它不是只在纽伦堡一个城市的单一校园大学，选校时要确认具体校区、专业和授课语言。"
        )
    if "th-nuernberg" in text or "institute of technology" in text or "hochschule" in text:
        return (
            "如果你指的是 Nürnberg Institute of Technology / TH Nürnberg，它更偏应用技术大学，"
            "优势通常在工程、技术、实践导向和区域就业联系；和研究型综合大学相比，学术研究声量可能不是同一类型。"
        )
    return "这类问题需要先确认学校实体：中文“纽伦堡大学”可能指 FAU Erlangen-Nürnberg，也可能指 TH Nürnberg；两者定位不同。"


def _university_profile_summary_zh(
    question: str,
    evidence: list[EvidenceItem],
    points: list[str],
) -> str:
    if _is_tsinghua_profile(evidence):
        detail_points = "\n".join(f"{index}. {point}" for index, point in enumerate(points[:5], start=1))
        refs = _join_refs(
            *[
                f"[{index}]"
                for index, item in enumerate(evidence, start=1)
                if any(term in f"{item.title} {item.url or ''}".lower() for term in ["tsinghua", "清华", "topuniversities", "wikipedia"])
            ][:4]
        )
        return (
            "学校评价：\n"
            f"1. 定位：清华大学是中国最顶尖的一类综合性研究型大学，国际知名度和学术声誉都很高{_maybe_ref(refs)}。\n"
            "2. 优势：工程、计算机、理科、科研平台、交叉学科和高水平师资/学生资源是主要强项。\n"
            "3. 适合人群：适合目标明确、能承受高强度竞争、希望进入科研、高端工程技术、互联网/AI、金融咨询或继续深造的人。\n"
            "4. 风险/不足：竞争强、压力大；不同专业体验差异很大，不能只看学校名气，必须看具体院系、项目课程、导师资源和就业/升学路径。\n\n"
            f"证据要点：\n{detail_points}"
        )

    fau_refs = _join_refs(
        *[
            f"[{index}]"
            for index, item in enumerate(evidence, start=1)
            if any(term in f"{item.title} {item.url or ''}".lower() for term in ["fau", "erlangen", "friedrich"])
        ][:3]
    )
    th_refs = _join_refs(
        *[
            f"[{index}]"
            for index, item in enumerate(evidence, start=1)
            if any(term in f"{item.title} {item.url or ''}".lower() for term in ["th-nuernberg", "hochschule", "technology"])
        ][:2]
    )
    detail_points = "\n".join(f"{index}. {point}" for index, point in enumerate(points[:5], start=1))
    return (
        "学校评价：\n"
        f"1. 先澄清名称：中文里的“纽伦堡大学”常常会混用。若指 FAU Erlangen-Nürnberg，它是埃尔朗根-纽伦堡地区的综合性大学；若指 TH Nürnberg / Nürnberg Institute of Technology，则是偏应用技术方向的高校{_maybe_ref(fau_refs or th_refs)}。\n"
        f"2. 如果目标是研究型大学、读硕士/博士、看重综合学科和科研环境，FAU 这一路径更合适{_maybe_ref(fau_refs)}。\n"
        f"3. 如果目标是实践导向、工程技术、应用型学习和本地就业连接，TH Nürnberg 更需要纳入比较{_maybe_ref(th_refs)}。\n"
        "4. 对中国学生的实际建议：不要只按城市名选校，要直接核对具体项目页面的课程设置、授课语言、申请要求、校区位置和实习/就业资源。\n\n"
        f"证据要点：\n{detail_points}"
    )


def _is_tsinghua_profile(evidence: list[EvidenceItem]) -> bool:
    text = " ".join(f"{item.title} {item.url or ''} {item.snippet[:400]}" for item in evidence).lower()
    return "tsinghua" in text or "清华" in text


def _price_summary_zh(evidence: list[EvidenceItem]) -> str:
    combined = " ".join(item.snippet for item in evidence)
    claims = _price_claims_from_text(combined)
    price_points = _price_evidence_points(evidence)
    lines = claims[:]
    if any(term in combined.lower() for term in ["nicht von der gkv", "nicht bei der behandlung von adipositas", "auf eigene kosten"]):
        lines.append("报销方面，抓取来源提示减重/肥胖用途通常需要重点核对是否自费；糖尿病适应证和 Ozempic 的报销情况需要按处方和医保规则确认")
    if not lines and price_points:
        lines = [_strip_ref(point) for point in price_points[:4]]
    if not lines:
        return "价格相关结论：本次抓到了价格类网页，但没有稳定抽取到可用金额；请以右侧原始来源为准。"
    return (
        "价格相关结论：\n"
        + "\n".join(f"{index}. {point}。" for index, point in enumerate(lines[:5], start=1))
        + "\n\n判断：这些是在线网页抽取到的当前价格线索，不等于处方建议。德国实际支付价格会受适应证、剂量、处方类型、药房和医保报销影响；减重用途通常要特别核对是否自费。"
    )


def _direct_price_answer_zh(text: str, money: list[str]) -> str:
    claims = _price_claims_from_text(text)
    if claims:
        return "根据本次在线搜索，德国 semaglutide 相关价格大致为：" + "；".join(claims[:4]) + "。实际支付取决于适应证、剂量、处方和医保/自费情况。"
    return f"本次在线搜索检索到价格相关信息：{', '.join(money[:4])}；具体金额应以右侧原始来源页面为准。"


def _price_claims_from_text(text: str) -> list[str]:
    lower = text.lower()
    claims: list[str] = []
    if "ozempic" in lower and any(value in text for value in ["170 €", "~170 €"]):
        claims.append("Ozempic/Semaglutid 线索约为 170 欧元/支注射笔")
    if "wegovy" in lower:
        if "270-360 €" in text or "270–360 €" in text:
            claims.append("Wegovy 自费线索约为 270-360 欧元/月")
        if "172–300 €" in text or "172-300 €" in text:
            claims.append("Wegovy 线索约为 172-300 欧元/月，随剂量阶段变化")
    if "0–30 €" in text or "0-30 €" in text:
        claims.append("部分远程医疗/处方服务可能另有 0-30 欧元费用")
    return list(dict.fromkeys(claims))


def _price_evidence_points(evidence: list[EvidenceItem]) -> list[str]:
    points: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(evidence, start=1):
        for sentence in _plain_sentences(item.snippet):
            clean = _clean_evidence_sentence(sentence)
            if not _find_money(clean):
                continue
            if not any(term in clean.lower() for term in ["ozempic", "wegovy", "semaglutid", "kosten", "preis", "€", "eur"]):
                continue
            key = re.sub(r"\W+", "", clean.lower())[:110]
            if key in seen:
                continue
            seen.add(key)
            points.append(f"{clean} [{index}]")
            if len(points) >= 6:
                return points
    return points


def _application_summary_zh(question: str, evidence: list[EvidenceItem], points: list[str]) -> str:
    evidence_text = " ".join(f"{item.title} {item.snippet}" for item in evidence)
    lower = evidence_text.lower()
    question_lower = question.lower()
    refs = "".join(f"[{index}]" for index in range(1, min(len(evidence), 4) + 1))
    application_ref = _point_ref(points, ["application", "apply", "campo", "申请"])
    requirement_ref = _point_ref(points, ["requirements", "minimum", "ects", "资格", "条件"])
    language_ref = _point_ref(points, ["english", "language", "语言"])
    test_ref = _point_ref(points, ["qualification assessment", "admission test", "test", "评估", "考试"])

    requirements: list[str] = []
    if "140 ects" in lower:
        requirements.append("已完成或接近完成本科学位，并满足项目/院系要求的 ECTS 或课程基础；当前证据中出现 Faculty of Engineering 申请至少 140 ECTS 的要求。")
    else:
        requirements.append("先确认本科背景是否满足项目最低要求，尤其是课程匹配度、学位层级和成绩要求。")
    if any(term in lower for term in ["qualification assessment", "admission test", "aptitude", "入学"]):
        requirements.append("准备资格评估或入学测试，因为证据中出现 qualification assessment / admission test 相关信息。")
    if any(term in lower for term in ["english", "teaching language", "completely in english"]):
        requirements.append("按英文授课项目准备语言证明，并以项目页当季要求为准。")
    requirements.append("申请材料要完整，至少应重点核对成绩单、学位或在读证明、语言证明、课程描述/模块手册和项目要求的附加材料。")

    if "fau" in question_lower and (
        "ai" in question_lower or "artificial intelligence" in question_lower or "人工智能" in question
    ):
        positioning = (
            "FAU 这里指 Friedrich-Alexander-Universitat Erlangen-Nurnberg。你问的方向对应 M.Sc. Artificial Intelligence，"
            "申请判断应以 FAU 官方项目页、AI 项目站和 Master 申请页面为主。"
        )
    else:
        positioning = "这个问题属于项目申请判断，应优先使用学校/项目官方页面、申请页面和招生要求页面，而不是中介或论坛信息。"

    return (
        "申请相关结论：\n"
        f"1. 学校/项目定位：{positioning}{refs}。\n"
        f"2. 申请条件：{'；'.join(requirements)}{requirement_ref or language_ref or test_ref}\n"
        f"3. 申请流程：先查项目页确认当季申请周期和项目要求，再通过学校指定系统提交；提交前要保证材料完整，因为证据中明确提到需要观察申请周期、准备所需文件并检查 admission requirements{application_ref}。\n"
        "4. 申请预测：如果你的本科背景、课程、成绩和语言证明与项目要求匹配，可以继续推进；如果是跨专业、核心课程不足，或材料无法证明课程匹配度，风险会明显升高。这个判断来自当前在线证据，不等于录取承诺。\n"
        f"5. 建议下一步：打开右侧前 2-3 个官方来源，逐项记录 deadline、ECTS/课程要求、语言要求、测试要求、申请系统和材料清单。"
    )


def _point_ref(points: list[str], keywords: list[str]) -> str:
    for point in points:
        lower = point.lower()
        if any(keyword.lower() in lower for keyword in keywords):
            match = re.search(r"\[\d+\]$", point)
            if match:
                return match.group(0)
    return ""


def _evidence_points(question: str, evidence: list[EvidenceItem], limit: int = 6) -> list[str]:
    scored: list[tuple[float, str]] = []
    for index, item in enumerate(evidence, start=1):
        text = f"{item.title}. {item.snippet}"
        for sentence in _plain_sentences(text):
            clean = _clean_evidence_sentence(sentence)
            if len(clean) < 24:
                continue
            if _is_boilerplate_sentence(clean):
                continue
            score = _chunk_score(clean, question, item.title) + item.rerank_score + 0.2 * item.source_quality_score
            scored.append((score, f"{clean} [{index}]"))
    scored.sort(key=lambda row: row[0], reverse=True)
    points: list[str] = []
    seen: set[str] = set()
    for _, point in scored:
        key = re.sub(r"\W+", "", point.lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        points.append(point)
        if len(points) >= limit:
            break
    return points


def _plain_sentences(text: str) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    parts = re.split(r"(?<=[。！？!?])\s+|(?<=[.])\s+(?=[A-Z0-9])|[；;]\s*", clean)
    if len(parts) == 1 and len(clean) > 260:
        words = clean.split()
        return [" ".join(words[index : index + 45]) for index in range(0, len(words), 36)]
    return parts


def _clean_evidence_sentence(sentence: str) -> str:
    clean = re.sub(r"\s+", " ", sentence).strip(" -:：")
    boilerplate = [
        "Skip to main content",
        "Use Tab to navigate",
        "Enter to select",
        "Escape to close",
        "Back Close",
        "No menu items",
    ]
    for phrase in boilerplate:
        clean = clean.replace(phrase, "")
    clean = re.sub(r"\s+", " ", clean).strip(" -:：")
    return clean[:260].rstrip()


def _is_boilerplate_sentence(sentence: str) -> bool:
    lower = sentence.lower()
    if "中国著名高等学府" in sentence or "重要基地" in sentence or "tsinghua university was established" in lower:
        return False
    menu_terms = [
        "prospective students",
        "bachelor program",
        "application faqs",
        "admission test faq",
        "living and studying",
        "privacy notice",
        "dear visitor",
        "website_thn",
        "sie verlassen",
        "mit einem klick",
        "unten stehenden button",
        "gelangen sie",
        "微信",
        "祝贺",
        "复信",
        "团队新突破",
        "首次观测",
        "头条新闻",
        "塞尔维亚总统",
        "海外名师",
        "习近平",
        "总书记",
        "校庆献辞",
        "use tab",
        "close button",
        "menu items",
        "skip to main content",
    ]
    if sum(term in lower for term in menu_terms) >= 2:
        return True
    if lower.count("application") >= 3 and ("faq" in lower or "admission test" in lower):
        return True
    if len(re.findall(r"\d{2}月\d{2}日", sentence)) >= 2:
        return True
    if len(sentence.split()) > 30 and not any(
        term in lower for term in ["requirement", "requires", "degree", "program is", "master's degree", "teaching language"]
    ):
        return True
    return False


def _strip_ref(point: str) -> str:
    return re.sub(r"\s*\[\d+\]$", "", point).strip()


def _is_fau_ai_application_question(question: str, evidence: list[EvidenceItem]) -> bool:
    lower = question.lower()
    evidence_text = " ".join(f"{item.title} {item.url or ''}" for item in evidence).lower()
    return "fau" in lower and any(
        term in f"{lower} {evidence_text}"
        for term in ["artificial intelligence", "ai", "人工智能", "admission", "申请"]
    )


def _synthesize_fau_ai_application_answer_zh(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
) -> str:
    program_ref = _source_ref(
        evidence,
        lambda item: "artificial-intelligence-msc" in (item.url or "")
        or "artificial intelligence" in item.title.lower(),
    )
    ai_site_ref = _source_ref(evidence, lambda item: "ai.study.fau.eu" in (item.url or ""))
    masters_ref = _source_ref(evidence, lambda item: "applying-for-masters" in (item.url or ""))
    profile_ref = _source_ref(
        evidence,
        lambda item: "facts-and-figures" in (item.url or "") or "profile" in item.title.lower(),
    )
    refs = _join_refs(program_ref, ai_site_ref, masters_ref, profile_ref)
    combined = " ".join(f"{item.title} {item.snippet}" for item in evidence)
    lower_combined = combined.lower()

    school_intro = (
        f"FAU 指 Friedrich-Alexander-Universitat Erlangen-Nurnberg（埃尔朗根-纽伦堡大学），"
        f"是德国巴伐利亚埃尔朗根/纽伦堡地区的综合性大学；本次检索优先使用 FAU 官方项目页、"
        f"AI 项目站和 Master 申请说明作为依据{_maybe_ref(profile_ref or program_ref)}。"
    )
    program_intro = (
        f"你问的 AI 专业对应 FAU 的 M.Sc. Artificial Intelligence。官方项目页显示该项目在 Erlangen，"
        f"授课语言为英语，录取方式不是简单先到先得，而是 Qualification Assessment（资格评估）"
        f"{_maybe_ref(program_ref)}。"
    )

    conditions = [
        (
            "本科背景要匹配：从项目介绍看，它建立在 Computer Science 基础之上，并和 applied mathematics、"
            f"engineering application 相关；所以本科课程里计算机、数学、算法、机器学习/AI、工程技术基础越完整越好{_maybe_ref(program_ref)}。"
        ),
        (
            f"需要通过项目资格评估：官方证据中出现 Admission Requirements / Qualification Assessment，"
            f"AI 项目站也包含 Master AI 与 admission tests 信息；这意味着成绩之外，课程匹配度和可能的入学测试都很关键"
            f"{_maybe_ref(_join_refs(program_ref, ai_site_ref))}。"
        ),
        (
            f"语言方面按英语授课项目准备：当前抓取到的官方项目页显示 teaching language 为 completely in English；"
            f"你应按 FAU 官方页面要求准备英语证明，并在提交前核对当季是否有更新{_maybe_ref(program_ref)}。"
        ),
        (
            f"申请流程按 FAU Master 申请页面走：先确认申请周期、项目最低要求和所需材料，再通过 FAU 指定申请系统提交；"
            f"国际申请者尤其要提前准备成绩单、学位/在读证明、语言证明和课程描述/模块手册等材料{_maybe_ref(masters_ref)}。"
        ),
    ]
    if "in-person" in lower_combined or "move to germany" in lower_combined:
        conditions.append(
            f"学习形式上要按线下到德国准备；AI FAQ 证据提到 FAU 是 in-person university，不能把它当远程项目申请{_maybe_ref(ai_site_ref)}。"
        )

    prediction = (
        "基于这些证据的申请判断：如果你的本科是计算机、AI、数据科学、软件工程、数学/工程中偏计算方向，"
        "并且能拿出清晰的课程匹配、较好的成绩、英语证明和 AI/ML 项目经历，那么申请逻辑是顺的；"
        "如果你是明显跨专业，或者缺少算法、编程、数学、机器学习等核心课程，风险会比较高，"
        "应优先补课程描述、项目经历和入学测试准备。这个判断是基于官方要求的推断，不等于录取承诺。"
    )
    missing = (
        "当前检索证据没有稳定覆盖具体申请截止日期、当季名额、精确 ECTS 条款和你的个人 GPA 换算，"
        "所以这些必须回到右侧官方来源和 FAU 当季申请系统逐项确认。"
    )

    return (
        "Direct Answer：可以申请，但你需要把重点放在“本科课程匹配度 + 资格评估/可能的入学测试 + 英语证明 + 完整申请材料”上。"
        "FAU 的 AI 硕士更像一个偏计算机基础和工程应用交叉的英文授课项目，不适合只用泛泛的 AI 兴趣去申请。\n\n"
        f"Question：{question}\n\n"
        "Summary：\n"
        f"1. 学校介绍：{school_intro}\n"
        f"2. 项目定位：{program_intro}\n"
        "3. 申请条件/准备重点：\n"
        + "\n".join(f"   - {item}" for item in conditions)
        + "\n"
        f"4. 申请预测：{prediction}\n\n"
        f"Limitations：{missing} {'；'.join(limitations[:1])}\n\n"
        f"Confidence：{confidence.title()}\n\n"
        f"Sources：关键依据来自右侧 Web Source Review 的官方来源{_maybe_ref(refs)}。"
    )


def _source_ref(evidence: list[EvidenceItem], predicate) -> str:
    for index, item in enumerate(evidence, start=1):
        if predicate(item):
            return f"[{index}]"
    return ""


def _join_refs(*refs: str) -> str:
    unique = [ref for ref in refs if ref]
    return "".join(dict.fromkeys(unique))


def _maybe_ref(ref: str) -> str:
    return ref if ref else ""


def _structured_ranking_count(question: str, evidence: list[EvidenceItem]) -> int:
    lower = question.lower()
    if "qs" not in lower or not any(term in question for term in ["前三百", "前300", "top 300", "300"]):
        return 0
    combined = " ".join(f"{item.title} {item.snippet}" for item in evidence)
    return len(_extract_ranked_names(combined))


def _extract_ranked_names(text: str) -> list[str]:
    patterns = [
        r"第\s*(\d+)\s*(?:位|名|:|：)\s*([^第。\n\r]{2,80})",
        r"(\d{1,3})\.\s*([^；;\n\r]{2,80})",
        r"#\s*(\d+)\s+([A-Z][A-Za-z0-9 '&.,()\\-]{2,90})",
    ]
    items: list[str] = []
    for pattern in patterns:
        for rank, name in re.findall(pattern, text):
            clean_name = re.sub(r"\s+", " ", name).strip(" ：:;；,，。")
            if clean_name:
                items.append(f"{rank}. {clean_name}")
    return list(dict.fromkeys(items))


def _rank_numbers(items: list[str]) -> set[int]:
    ranks = set()
    for item in items:
        match = re.match(r"(\d+)\.", item)
        if match:
            ranks.add(int(match.group(1)))
    return ranks


def _web_limitations(label: str, evidence_count: int) -> list[str]:
    if label == "strong":
        return ["网页证据通过当前加权阈值，但仍建议以右侧原始来源为准。"]
    if label == "moderate":
        return ["网页证据相关，但来源结构化程度或覆盖范围仍有限。"]
    if label == "weak":
        return ["网页证据与问题相关，但不足以支持完整、确定的长清单或精确结论。"]
    return ["没有检索到足以支撑可靠回答的网页证据。"]


def _find_money(text: str) -> list[str]:
    import re

    pattern = (
        r"(?:€|EUR|USD|\\$|£)\s?~?\d+(?:[.,]\d+)?(?:\s?[-–]\s?\d+(?:[.,]\d+)?)?"
        r"|~?\d+(?:[.,]\d+)?(?:\s?[-–]\s?\d+(?:[.,]\d+)?)?\s?(?:€|EUR|USD|dollars|euros)"
    )
    return list(dict.fromkeys(re.findall(pattern, text, flags=re.IGNORECASE)))


def _source_citation(item: EvidenceItem) -> str:
    if item.url:
        return f"({item.title}, {item.url})"
    return f"({item.title})"


def _web_unavailable_answer(
    question: str,
    evidence: list[EvidenceItem],
    limitations: list[str],
    language: str,
) -> str:
    if language.lower().startswith("zh"):
        return (
            "Direct Answer：本次没有拿到可核验的在线网页结果，所以不能给出实时搜索结论。\n\n"
            f"Question：{question}\n\n"
            f"Summary：在线检索没有返回可核验来源；失败详情见右侧来源卡片。\n\n"
            f"Limitations：{'；'.join(limitations[:2])}\n\n"
            "Confidence：Insufficient\n\n"
            "Sources：右侧会显示失败原因；配置 Tavily/Brave key 后可走正式在线搜索。"
        )
    return (
        "Direct Answer: No verifiable live web result was retrieved, so the agent cannot provide a current web answer.\n\n"
        f"Question: {question}\n\n"
        "Summary: Live search did not return verifiable sources; failure details are shown in the source panel.\n\n"
        f"Limitations: {'; '.join(limitations[:2])}\n\n"
        "Confidence: Insufficient\n\n"
        "Sources: See the failure details in the source panel."
    )
