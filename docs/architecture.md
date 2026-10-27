# Architecture

```mermaid
flowchart TD
  U["User"] --> F["Next.js Web UI"]
  F --> B["FastAPI Backend"]
  B --> R["Query Router"]
  R --> MR["Medical RAG Pipeline"]
  R --> WS["Web Search Agent"]
  R --> HY["Hybrid Mode"]
  MR --> PM["PubMed / Europe PMC Search"]
  MR --> RET["Hybrid Retrieval + Reranking"]
  WS --> API["Tavily / Brave / no-key fallback"]
  WS --> CR["Source Credibility Ranking"]
  RET --> G["Evidence Confidence Gate"]
  CR --> G
  G --> A["Cited Answer"]
  B --> PG["PostgreSQL"]
  B --> Q["Qdrant"]
  B --> RD["Redis"]
  B --> MN["MinIO"]
```

The MVP keeps persistence in memory so the app can be started quickly. The SQLAlchemy models and Docker services are already included so PostgreSQL/Qdrant integration can be added without changing the API contract.

## Backend Modules

- `api/routes.py`: public API endpoints
- `agents/router.py`: query type and risk routing
- `agents/web_search_agent.py`: search planning, web search, source ranking, synthesis
- `rag/pipeline.py`: literature search, retrieval, confidence gate, answer generation
- `rag/confidence.py`: evidence gate formula and answer labels
- `search/pubmed.py`: Europe PMC client with explicit demo fallback only when live literature access fails
- `search/web.py`: Tavily/Brave client with no-key fallback and explicit insufficient-evidence failure state
- `services/store.py`: MVP in-memory trace and evidence store

## Frontend Modules

- `/chat`: main agent workspace
- `/web-search`: dedicated dynamic Web Search Agent
- `/medical-rag`: dedicated Medical RAG Agent
- `/literature`: PubMed / Europe PMC search
- `/evidence`: local evidence library
- `/evaluation`: trace-derived metrics dashboard
- `/settings`: deployment and runtime configuration
