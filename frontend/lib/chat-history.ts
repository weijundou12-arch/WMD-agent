import type { AgentMode, ChatResponse, EvidenceStrictness, RetrievalLevel } from "./types";

export type ChatEndpoint = "chat" | "web" | "medical";

export type StoredConversationRun = {
  question: string;
  response: ChatResponse;
};

export type StoredChatSession = {
  id: string;
  endpoint: ChatEndpoint;
  title: string;
  route: string;
  mode: AgentMode;
  retrieval: RetrievalLevel;
  strictness: EvidenceStrictness;
  createdAt: string;
  updatedAt: string;
  runs: StoredConversationRun[];
};

const HISTORY_KEY = "wmd-agent:chat-history:v1";

export function makeSessionId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function getAllSessions(): StoredChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const saved = window.localStorage.getItem(HISTORY_KEY);
    if (!saved) return [];
    const parsed = JSON.parse(saved) as StoredChatSession[];
    if (!Array.isArray(parsed)) return [];
    return parsed.sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
  } catch {
    return [];
  }
}

export function getSession(id: string) {
  return getAllSessions().find((session) => session.id === id);
}

export function getSessionsByEndpoint(endpoint: ChatEndpoint) {
  return getAllSessions().filter((session) => session.endpoint === endpoint);
}

export function saveSession(session: StoredChatSession) {
  if (typeof window === "undefined") return;
  const sessions = getAllSessions();
  const next = [session, ...sessions.filter((item) => item.id !== session.id)]
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
    .slice(0, 80);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
}

export function deleteSession(id: string) {
  if (typeof window === "undefined") return;
  const sessions = getAllSessions().filter((session) => session.id !== id);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(sessions));
}

export function endpointRoute(endpoint: ChatEndpoint) {
  if (endpoint === "web") return "/web-search";
  if (endpoint === "medical") return "/medical-rag";
  return "/chat";
}

export function endpointLabel(endpoint: ChatEndpoint) {
  if (endpoint === "web") return "Web Search";
  if (endpoint === "medical") return "Medical RAG";
  return "Agent";
}

export function titleFromRuns(runs: StoredConversationRun[]) {
  const firstQuestion = runs[runs.length - 1]?.question || "Untitled conversation";
  return firstQuestion.length > 42 ? `${firstQuestion.slice(0, 41)}...` : firstQuestion;
}
