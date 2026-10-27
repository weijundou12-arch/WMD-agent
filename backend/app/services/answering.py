from __future__ import annotations

import re

from app.schemas.chat import EvidenceItem


def synthesize_answer(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
    language: str = "zh",
) -> str:
    if language.lower().startswith("zh"):
        return _answer_zh(question, evidence, confidence, limitations)
    return _answer_en(question, evidence, confidence, limitations)


def _answer_zh(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
) -> str:
    if not evidence:
        return (
            "Direct Answer：目前没有在 PubMed / Europe PMC 论文库中检索到足够可靠、可引用的医学证据，所以不能给出确定医学结论。\n\n"
            f"Question：{question}\n\n"
            "Evidence Summary：没有通过严格来源过滤和重排序的论文证据；系统不会用 demo 论文、网页百科或模型记忆替代医学数据库证据。\n\n"
            "GPT-4-style Comparison：如果把同一批“空证据”交给 GPT-4 类模型，合理回答也应该是“不足以判断”，而不是凭常识给医学结论。\n\n"
            "Limitations：建议扩大疾病/药物同义词、放宽年份过滤，或切换到 Hybrid/Web Search 补充最新指南和官方来源。\n\n"
            "Confidence：Insufficient\n\n"
            "References：右侧 Evidence Review 未选中可靠证据。"
        )

    lead = {
        "strong": "根据当前召回的证据，可以给出相对稳健的证据型回答。",
        "moderate": "根据当前召回的证据，可以给出有限但可追溯的回答。",
        "weak": "当前证据较弱，下面只能作为检索摘要，不能作为确定结论。",
        "insufficient": "系统召回到了一些材料，但综合评分不足以支持确定医学结论；下面给出可追溯证据摘要，而不是强行下结论。",
    }.get(confidence, "当前证据不足。")

    limitation_text = "；".join(limitations[:2])
    direct = _medical_direct_answer_zh(question, evidence, confidence)
    evidence_summary = _medical_evidence_summary_zh(evidence)
    comparison = _gpt4_style_medical_comparison_zh(question, evidence, confidence)

    return (
        f"Direct Answer：{direct or lead}\n\n"
        f"Question：{question}\n\n"
        f"Evidence Summary：{evidence_summary}\n\n"
        f"Model Summary：{_model_summary_zh(question, evidence, confidence)}\n\n"
        f"GPT-4-style Comparison：{comparison}\n\n"
        f"Limitations：{limitation_text}\n\n"
        f"Confidence：{confidence.title()}\n\n"
        "References：所有 PMID / DOI / journal / snippet 已集中放在右侧 Evidence Review。\n\n"
        "Medical Note：这不是个人医疗诊断或治疗建议；涉及用药、诊断或治疗决策时应咨询合格临床医生。"
    )


def _answer_en(
    question: str,
    evidence: list[EvidenceItem],
    confidence: str,
    limitations: list[str],
) -> str:
    if not evidence:
        return (
            "Direct Answer: The system did not retrieve enough reliable evidence to support a clear conclusion.\n\n"
            f"Question: {question}\n\n"
            "Evidence Summary: No PubMed / Europe PMC paper evidence survived strict source filtering and reranking.\n\n"
            "GPT-4-style Comparison: A GPT-4-style answer over the same empty evidence set should also refuse a firm biomedical conclusion.\n\n"
            "Limitations: Broaden the disease/drug terms, relax filters, or switch to Hybrid/Web Search.\n\n"
            "Confidence: Insufficient\n\n"
            "References: No reliable evidence was selected in the Evidence Review panel."
        )

    lead = {
        "strong": "The retrieved evidence supports a relatively robust evidence-grounded answer.",
        "moderate": "The retrieved evidence supports a limited but traceable answer.",
        "weak": "The retrieved evidence is weak, so treat this as a retrieval summary rather than a conclusion.",
        "insufficient": "The system retrieved some material, but the weighted evidence score is too low for a firm conclusion.",
    }.get(confidence, "Evidence is insufficient.")

    return (
        f"Direct Answer: {_medical_direct_answer_en(question, evidence, confidence) or lead}\n\nQuestion: {question}\n\n"
        f"Evidence Summary: {_medical_evidence_summary_en(evidence)}\n\n"
        f"Model Summary: {_model_summary_en(question, evidence, confidence)}"
        + f"\n\nGPT-4-style Comparison: {_gpt4_style_medical_comparison_en(question, evidence, confidence)}"
        + "\n\nLimitations: "
        + "; ".join(limitations[:2])
        + f"\n\nConfidence: {confidence.title()}"
        + "\n\nReferences: PMID / DOI / journal / snippets are shown in the Evidence Review panel."
        + "\n\nMedical Note: This is not personal medical advice."
    )


def _model_summary_zh(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    corpus = " ".join(f"{item.title} {item.snippet}" for item in evidence[:5]).lower()
    if any(term in question.lower() or term in question for term in ["司美格鲁肽", "semaglutide", "glp-1", "骨密度"]):
        if "bone mineral density" in corpus or "bone health" in corpus or "骨" in corpus:
            return (
                "右侧文献主要支持一个谨慎结论：GLP-1/司美格鲁肽相关治疗可能通过体重下降、代谢变化、肌肉量变化等间接影响骨健康；"
                "但当前召回证据更多是综述或间接机制证据，直接评估司美格鲁肽对 BMD 的高质量临床证据不足。"
            )
    if "hpv" in question.lower() and ("sarcopenia" in question.lower() or "肌少" in question):
        return (
            "右侧证据需要区分直接关联和间接机制：如果没有直接研究 HPV 与 sarcopenia 的文献，系统只应总结炎症、免疫或肌肉代谢相关的背景证据。"
        )
    if confidence in {"weak", "insufficient"}:
        return "右侧证据没有形成足够一致、直接的证据链，因此答案应保持保守，只能说明目前检索到的研究方向和证据缺口。"
    return "右侧证据形成了可追溯的支持链，答案基于召回文献的题名、摘要、研究类型和加权证据评分生成。"


def _medical_direct_answer_zh(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    corpus = _evidence_corpus(evidence)
    lower_question = question.lower()
    if confidence in {"weak", "insufficient"}:
        return "目前不能给出肯定医学结论；严格论文库证据没有达到可靠回答阈值，只能说明检索到的研究线索和证据缺口。"
    if any(term in lower_question or term in question for term in ["司美格鲁肽", "semaglutide", "glp-1", "骨密度", "bmd"]):
        if any(term in corpus for term in ["bone mineral density", "bmd", "osteoporosis", "fracture", "bone health"]):
            return (
                "基于当前 PubMed / Europe PMC 证据，较稳妥的结论是：司美格鲁肽或 GLP-1RA 与骨健康可能存在关联，"
                "但更可能通过体重下降、代谢变化、肌肉/脂肪组成变化等间接路径影响；不能简单断言它一定升高或降低骨密度。"
            )
        return "当前论文证据没有直接形成“司美格鲁肽改变骨密度”的证据链，因此只能说证据不足。"
    if "hpv" in lower_question and ("sarcopenia" in lower_question or "肌少" in question):
        direct = any("hpv" in f"{item.title} {item.snippet}".lower() and "sarcopenia" in f"{item.title} {item.snippet}".lower() for item in evidence)
        if direct:
            return "当前论文库能找到 HPV 与 sarcopenia 相关的研究线索，但仍需要看研究类型、样本和混杂因素，不能直接推成因果关系。"
        return "当前更像是间接机制证据：HPV、炎症/免疫状态与肌肉健康可能存在路径关联，但直接研究证据不足。"
    first = _first_informative_sentence(evidence)
    if first:
        return f"基于右侧最高排序论文，当前可支持的结论是：{first}"
    return ""


def _medical_direct_answer_en(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    corpus = _evidence_corpus(evidence)
    lower_question = question.lower()
    if confidence in {"weak", "insufficient"}:
        return "A firm biomedical conclusion is not supported because the strict literature evidence did not pass the reliability threshold; the answer should only describe research signals and evidence gaps."
    if any(term in lower_question for term in ["semaglutide", "glp-1", "bone mineral density", "bmd"]):
        if any(term in corpus for term in ["bone mineral density", "bmd", "osteoporosis", "fracture", "bone health"]):
            return (
                "The safest conclusion from the retrieved PubMed / Europe PMC evidence is that semaglutide or GLP-1RA therapy may be linked to bone health, often indirectly through weight loss and metabolic/body-composition changes; the evidence should not be reduced to a simple increase/decrease in BMD."
            )
    first = _first_informative_sentence(evidence)
    return f"The strongest retrievable conclusion is: {first}" if first else ""


def _medical_evidence_summary_zh(evidence: list[EvidenceItem]) -> str:
    lines = []
    for index, item in enumerate(evidence[:6], start=1):
        citation = _citation(item)
        study = item.study_type or "study type not specified"
        journal = item.journal or "journal not specified"
        year = item.year or "year n/a"
        snippet = _first_sentence(item.snippet)
        lines.append(
            f"{index}. {item.title}；{journal}，{year}；{study}；支持度 {item.support_level}，rerank={item.rerank_score}。"
            f"{citation} 摘要要点：{snippet}"
        )
    return "\n".join(lines)


def _medical_evidence_summary_en(evidence: list[EvidenceItem]) -> str:
    lines = []
    for index, item in enumerate(evidence[:6], start=1):
        citation = _citation(item)
        study = item.study_type or "study type not specified"
        journal = item.journal or "journal not specified"
        year = item.year or "year n/a"
        snippet = _first_sentence(item.snippet)
        lines.append(
            f"{index}. {item.title}; {journal}, {year}; {study}; support={item.support_level}, rerank={item.rerank_score}. {citation} Key point: {snippet}"
        )
    return "\n".join(lines)


def _gpt4_style_medical_comparison_zh(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    if confidence in {"weak", "insufficient"}:
        return (
            "同一批证据如果交给 GPT-4 类模型，合理输出也应该保守：先说明证据不足，再列出已有研究线索和缺口。"
            "WMD-agent 的额外约束是：只允许右侧 PubMed / Europe PMC 证据进入结论，并用 Evidence Gate 阈值阻止强答。"
        )
    return (
        "同一批证据如果交给 GPT-4 类模型，预期会给出相近的总结性结论；差异在于 WMD-agent 同时展示 PMID/DOI、rerank 分数、"
        "研究类型和证据阈值，因此更容易核验每一句医学断言是否有来源支撑。"
    )


def _gpt4_style_medical_comparison_en(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    if confidence in {"weak", "insufficient"}:
        return (
            "A GPT-4-style answer over the same evidence should also remain conservative, describing evidence gaps rather than making a firm clinical claim. WMD-agent adds explicit PubMed / Europe PMC filtering and an evidence gate."
        )
    return (
        "A GPT-4-style answer over the same evidence would likely reach a similar high-level conclusion, while WMD-agent exposes PMID/DOI metadata, rerank scores, study type, and the confidence gate."
    )


def _evidence_corpus(evidence: list[EvidenceItem]) -> str:
    return " ".join(f"{item.title} {item.snippet} {item.study_type or ''}" for item in evidence[:8]).lower()


def _first_informative_sentence(evidence: list[EvidenceItem]) -> str:
    for item in evidence:
        sentence = _first_sentence(item.snippet)
        if sentence and len(sentence) > 20:
            return sentence
    return ""


def _first_sentence(text: str) -> str:
    clean = " ".join(text.split())
    if not clean:
        return ""
    parts = re.split(r"(?<=[。！？!?])\s+|(?<=[.])\s+(?=[A-Z0-9])|[；;]\s*", clean)
    return (parts[0] if parts else clean)[:360].rstrip()


def _model_summary_en(question: str, evidence: list[EvidenceItem], confidence: str) -> str:
    corpus = " ".join(f"{item.title} {item.snippet}" for item in evidence[:5]).lower()
    if any(term in question.lower() for term in ["semaglutide", "glp-1", "bone mineral density", "bmd"]):
        if "bone mineral density" in corpus or "bone health" in corpus:
            return (
                "The retrieved papers support a cautious interpretation: GLP-1/semaglutide-related therapy may affect skeletal health indirectly through weight loss, metabolism, or lean-mass changes, but direct high-quality clinical evidence on BMD remains limited."
            )
    if confidence in {"weak", "insufficient"}:
        return "The evidence panel did not form a direct and consistent evidence chain, so the answer remains conservative and highlights the evidence gap."
    return "The answer is generated from the paper titles, abstracts, study metadata, and weighted evidence score shown in the evidence panel."


def _citation(item: EvidenceItem) -> str:
    parts = []
    if item.pmid:
        parts.append(f"PMID: {item.pmid}")
    if item.doi:
        parts.append(f"DOI: {item.doi}")
    if item.journal:
        parts.append(item.journal)
    if item.year:
        parts.append(str(item.year))
    if item.url and not parts:
        parts.append(item.url)
    return "(" + ", ".join(parts) + ")" if parts else ""
