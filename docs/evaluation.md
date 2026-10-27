# Evaluation

The MVP dashboard stores trace-derived placeholder metrics. For real evaluation, create a benchmark set with questions, relevant PMID/DOI labels, and expected answer support.

## Metrics

| Metric | Purpose |
| --- | --- |
| retrieval recall@k | Whether relevant evidence is retrieved |
| MRR / nDCG | Whether relevant evidence ranks high |
| faithfulness | Whether answer claims are supported |
| citation precision | Whether citations support the cited sentence |
| answer relevancy | Whether the answer addresses the question |
| hallucination rate | Unsupported claim rate |
| latency | End-to-end response time |
| cost | Search/model API cost |

## Suggested Flow

1. Save every QA run with route, evidence, answer, latency, and model version.
2. Label a small gold dataset manually.
3. Run Basic vs Advanced RAG on the same dataset.
4. Evaluate retrieval and generation separately.
5. Track regressions in CI.
