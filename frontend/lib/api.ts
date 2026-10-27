import type { ChatRequest, ChatResponse, EvalRun, EvidenceItem, Paper } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function sendChat(request: ChatRequest) {
  return apiFetch<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export function sendWebAsk(request: ChatRequest) {
  return apiFetch<ChatResponse>("/api/web/ask", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export function sendMedicalAsk(request: ChatRequest) {
  return apiFetch<ChatResponse>("/api/medical/ask", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export function searchPapers(query: string) {
  return apiFetch<{ query: string; results: Paper[] }>("/api/search/pubmed", {
    method: "POST",
    body: JSON.stringify({
      query,
      max_results: 12,
      filters: { study_type: [], open_access_only: false }
    })
  });
}

export function listPapers() {
  return apiFetch<{ results: Paper[] }>("/api/papers");
}

export function getEvidence(answerId: string) {
  return apiFetch<{ answer_id: string; evidence: EvidenceItem[] }>(`/api/evidence/${answerId}`);
}

export function listEvalRuns() {
  return apiFetch<{ results: EvalRun[] }>("/api/eval/runs");
}

export function runEvaluation() {
  return apiFetch<EvalRun>("/api/eval/run", { method: "POST" });
}

export const apiBaseUrl = API_BASE;
