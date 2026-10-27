# RAG Methods

## Basic RAG

1. Search PubMed / Europe PMC.
2. Fetch title, abstract, metadata, PMID, DOI, journal, year.
3. Chunk title and abstract.
4. Score with lexical retrieval.
5. Rerank with metadata and relevance heuristics.
6. Apply evidence confidence gate.
7. Generate citation-grounded answer.

## Advanced RAG

The MVP implements engineering hooks for:

- Query rewriting / multi-query retrieval
- Corrective retrieval when confidence is weak
- Source quality and recency scoring
- Evidence consistency scoring

Planned production extensions:

- Dense retrieval with BGE-M3 / MedCPT / SPECTER2
- Qdrant hybrid dense + sparse + multivector retrieval
- Cross-encoder reranker
- HyDE query document generation
- Contextual Retrieval headers before embedding
- Self-RAG style support checks
- RAPTOR tree summaries for long papers
- GraphRAG for biomedical entity relationships

## PMC Compliance

Do not bulk crawl PMC article pages. For full-text ingestion, use PMC Open Access Subset and official bulk/OAI/FTP/cloud service paths. Store license metadata with each full-text document.
