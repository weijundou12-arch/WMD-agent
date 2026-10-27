from __future__ import annotations

import httpx

from app.core.config import Settings
from app.schemas.chat import EvidenceItem


async def generate_grounded_web_summary(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
    language: str,
    settings: Settings,
    contextual_question: str | None = None,
) -> str | None:
    if not settings.openai_api_key:
        return None

    sources = _format_sources(evidence[:8])
    system_prompt = (
        "You are WMD-agent, an evidence-first web search agent. "
        "Answer only from the supplied web evidence. Do not invent facts. "
        "If the evidence is incomplete, state that clearly. "
        "Do not paste raw evidence blocks; synthesize a user-facing answer like ChatGPT or DeepSeek. "
        "Cite source numbers such as [1], [2]."
    )
    if language.lower().startswith("zh"):
        user_prompt = (
            f"用户问题：{question}\n\n"
            f"上下文化检索问题：{contextual_question or question}\n\n"
            f"证据强度：{confidence}\n"
            f"限制：{'；'.join(limitations[:3])}\n\n"
            f"网页证据：\n{sources}\n\n"
            "请用中文输出：\n"
            "Direct Answer：直接回答用户问题。\n"
            "Summary：综合说明，像聊天模型最终回答，不要复制证据原文。\n"
            "Limitations：说明证据不足或来源限制。\n"
            "Confidence：Strong/Moderate/Weak/Insufficient。\n"
            "Sources：提示完整来源在右侧 Evidence Review。"
        )
    else:
        user_prompt = (
            f"Question: {question}\n\n"
            f"Confidence: {confidence}\n"
            f"Limitations: {'; '.join(limitations[:3])}\n\n"
            f"Evidence:\n{sources}\n\n"
            "Return: Direct Answer, Summary, Limitations, Confidence, Sources."
        )

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1400,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    return content.strip() or None


def _format_sources(evidence: list[EvidenceItem]) -> str:
    lines = []
    for index, item in enumerate(evidence, start=1):
        source = item.url or item.title
        lines.append(
            f"[{index}] title={item.title}\n"
            f"url={source}\n"
            f"support={item.support_level}; retrieval={item.retrieval_score}; "
            f"rerank={item.rerank_score}; quality={item.source_quality_score}\n"
            f"snippet={item.snippet[:900]}"
        )
    return "\n\n".join(lines)
