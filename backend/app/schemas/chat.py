from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AgentMode = Literal["auto", "medical_rag", "web_search", "hybrid"]
RetrievalLevel = Literal["basic", "advanced"]
EvidenceStrictness = Literal["low", "medium", "high"]
QueryType = Literal[
    "medical_literature_rag",
    "web_search",
    "hybrid",
    "safe_response",
]
RiskLevel = Literal["low", "medical_low", "medical_high_stakes"]
ConfidenceLabel = Literal["strong", "moderate", "weak", "insufficient"]


class SearchFilters(BaseModel):
    year_from: int | None = None
    year_to: int | None = None
    study_type: list[str] = Field(default_factory=list)
    open_access_only: bool = False


class ConversationTurn(BaseModel):
    question: str
    answer: str | None = None
    route: QueryType | None = None
    confidence: ConfidenceLabel | None = None
    evidence_titles: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    mode: AgentMode = "auto"
    retrieval_level: RetrievalLevel = "basic"
    evidence_strictness: EvidenceStrictness = "high"
    language: str = "zh"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)


class RouteDecision(BaseModel):
    query_type: QueryType
    need_web_search: bool
    need_pubmed: bool
    need_fulltext: bool
    risk_level: RiskLevel
    language: str
    rationale: str


class EvidenceItem(BaseModel):
    id: str
    title: str
    source_type: Literal["paper", "web", "guideline", "demo"] = "paper"
    url: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    journal: str | None = None
    year: int | None = None
    study_type: str | None = None
    snippet: str
    section: str | None = None
    support_level: Literal["direct", "partial", "indirect", "background", "conflicting"] = "background"
    retrieval_score: float = Field(ge=0, le=1)
    rerank_score: float = Field(ge=0, le=1)
    source_quality_score: float = Field(default=0.5, ge=0, le=1)


class TraceStep(BaseModel):
    name: str
    status: Literal["ok", "warning", "skipped", "error"]
    detail: str
    elapsed_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    confidence: ConfidenceLabel
    confidence_score: float = Field(ge=0, le=1)
    route: QueryType
    evidence: list[EvidenceItem]
    limitations: list[str]
    trace_id: str
    route_decision: RouteDecision
    trace: list[TraceStep]
    latency_ms: int
    cost_usd: float = 0
    model_version: str = "deterministic-evidence-synthesizer-v1"


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    max_results: int = Field(default=8, ge=1, le=20)


class PubMedSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    max_results: int = Field(default=10, ge=1, le=50)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class Paper(BaseModel):
    id: str
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str
    abstract: str = ""
    journal: str | None = None
    publication_year: int | None = None
    authors: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    publication_type: str | None = None
    is_open_access: bool = False
    source: str = "europe_pmc"
    url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IngestRequest(BaseModel):
    paper: Paper
    full_text: str | None = None


class IngestResponse(BaseModel):
    paper_id: str
    chunk_count: int
    status: Literal["stored", "updated"]


class EvalRun(BaseModel):
    id: str
    created_at: datetime
    total_runs: int
    faithfulness: float
    citation_precision: float
    answer_relevancy: float
    mean_latency_ms: float
    notes: list[str] = Field(default_factory=list)
