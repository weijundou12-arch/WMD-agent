export type AgentMode = "auto" | "medical_rag" | "web_search" | "hybrid";
export type RetrievalLevel = "basic" | "advanced";
export type EvidenceStrictness = "low" | "medium" | "high";
export type ConfidenceLabel = "strong" | "moderate" | "weak" | "insufficient";

export interface SearchFilters {
  year_from?: number | null;
  year_to?: number | null;
  study_type: string[];
  open_access_only: boolean;
}

export interface ConversationTurn {
  question: string;
  answer?: string | null;
  route?: RouteDecision["query_type"] | null;
  confidence?: ConfidenceLabel | null;
  evidence_titles: string[];
}

export interface ChatRequest {
  question: string;
  mode: AgentMode;
  retrieval_level: RetrievalLevel;
  evidence_strictness: EvidenceStrictness;
  language: string;
  filters: SearchFilters;
  conversation_history: ConversationTurn[];
}

export interface RouteDecision {
  query_type: "medical_literature_rag" | "web_search" | "hybrid" | "safe_response";
  need_web_search: boolean;
  need_pubmed: boolean;
  need_fulltext: boolean;
  risk_level: "low" | "medical_low" | "medical_high_stakes";
  language: string;
  rationale: string;
}

export interface EvidenceItem {
  id: string;
  title: string;
  source_type: "paper" | "web" | "guideline" | "demo";
  url?: string | null;
  pmid?: string | null;
  pmcid?: string | null;
  doi?: string | null;
  journal?: string | null;
  year?: number | null;
  study_type?: string | null;
  snippet: string;
  section?: string | null;
  support_level: "direct" | "partial" | "indirect" | "background" | "conflicting";
  retrieval_score: number;
  rerank_score: number;
  source_quality_score: number;
}

export interface TraceStep {
  name: string;
  status: "ok" | "warning" | "skipped" | "error";
  detail: string;
  elapsed_ms?: number | null;
  metadata: Record<string, unknown>;
}

export interface ChatResponse {
  answer: string;
  confidence: ConfidenceLabel;
  confidence_score: number;
  route: RouteDecision["query_type"];
  evidence: EvidenceItem[];
  limitations: string[];
  trace_id: string;
  route_decision: RouteDecision;
  trace: TraceStep[];
  latency_ms: number;
  cost_usd: number;
  model_version: string;
}

export interface Paper {
  id: string;
  pmid?: string | null;
  pmcid?: string | null;
  doi?: string | null;
  title: string;
  abstract: string;
  journal?: string | null;
  publication_year?: number | null;
  authors: string[];
  mesh_terms: string[];
  publication_type?: string | null;
  is_open_access: boolean;
  source: string;
  url?: string | null;
  created_at: string;
}

export interface EvalRun {
  id: string;
  created_at: string;
  total_runs: number;
  faithfulness: number;
  citation_precision: number;
  answer_relevancy: number;
  mean_latency_ms: number;
  notes: string[];
}
