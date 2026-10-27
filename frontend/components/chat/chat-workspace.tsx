"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import {
  Activity,
  BookOpenCheck,
  Clock3,
  FileSearch,
  Gauge,
  Layers3,
  Loader2,
  MessageSquarePlus,
  MessagesSquare,
  Network,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";
import { sendChat, sendMedicalAsk, sendWebAsk } from "@/lib/api";
import type {
  AgentMode,
  ChatRequest,
  ChatResponse,
  ConversationTurn,
  EvidenceStrictness,
  RetrievalLevel
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EvidenceCard } from "@/components/evidence/evidence-card";
import { cn } from "@/lib/utils";
import {
  getSession,
  getSessionsByEndpoint,
  makeSessionId,
  saveSession,
  titleFromRuns,
  type ChatEndpoint,
  type StoredChatSession
} from "@/lib/chat-history";

const sampleQuestions = [
  "GLP-1 药物和骨密度之间有没有关系？",
  "德国司美格鲁肽目前多少钱？",
  "2025 年以后 RAG 在医疗 QA 里的最新进展是什么？"
];

const defaultSteps = [
  "Understanding question",
  "Planning search queries",
  "Retrieving evidence",
  "Reranking sources",
  "Checking evidence sufficiency",
  "Generating cited answer"
];

type ChatWorkspaceProps = {
  title?: string;
  workspaceTitle?: string;
  panelTitle?: string;
  initialMode?: AgentMode;
  lockMode?: boolean;
  endpoint?: "chat" | "web" | "medical";
  defaultRetrieval?: RetrievalLevel;
  answerOnly?: boolean;
  examples?: string[];
  plannedSteps?: string[];
};

type ConversationRun = {
  question: string;
  response: ChatResponse;
};

export function ChatWorkspace({
  title = "Agent Workspace",
  workspaceTitle = "Evidence Run",
  panelTitle = "Source Review",
  initialMode = "auto",
  lockMode = false,
  endpoint = "chat",
  defaultRetrieval = "advanced",
  answerOnly = false,
  examples = sampleQuestions,
  plannedSteps = defaultSteps
}: ChatWorkspaceProps = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sessionParam = searchParams.get("session");
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<AgentMode>(initialMode);
  const [retrieval, setRetrieval] = useState<RetrievalLevel>(defaultRetrieval);
  const [strictness, setStrictness] = useState<EvidenceStrictness>("high");
  const [runs, setRuns] = useState<ConversationRun[]>([]);
  const [sessionId, setSessionId] = useState(() => makeSessionId());
  const [recentSessions, setRecentSessions] = useState<StoredChatSession[]>([]);

  const mutation = useMutation({
    mutationFn: (payload: ChatRequest) => {
      if (endpoint === "web") {
        return sendWebAsk(payload);
      }
      if (endpoint === "medical") {
        return sendMedicalAsk(payload);
      }
      return sendChat(payload);
    },
    onSuccess: (response, payload) => {
      setRuns((current) => [{ question: payload.question, response }, ...current]);
      setQuestion("");
    }
  });

  const active = runs[0]?.response;
  const visibleResponse = mutation.isPending ? undefined : active;
  const pendingQuestion = mutation.isPending ? mutation.variables?.question : undefined;
  const canSubmit = question.trim().length > 2 && !mutation.isPending;
  const conversationHistory = useMemo(() => buildConversationHistory(runs), [runs]);

  useEffect(() => {
    setRecentSessions(getSessionsByEndpoint(endpoint));
  }, [endpoint]);

  useEffect(() => {
    if (!sessionParam) {
      setRuns([]);
      setQuestion("");
      setSessionId(makeSessionId());
      setRecentSessions(getSessionsByEndpoint(endpoint));
      return;
    }

    const saved = getSession(sessionParam);
    if (!saved || saved.endpoint !== endpoint) {
      setRuns([]);
      setQuestion("");
      setSessionId(makeSessionId());
      setRecentSessions(getSessionsByEndpoint(endpoint));
      return;
    }

    setSessionId(saved.id);
    setRuns(saved.runs.slice(0, 12));
    setMode(lockMode ? initialMode : saved.mode);
    setRetrieval(saved.retrieval);
    setStrictness(saved.strictness);
    setQuestion("");
    setRecentSessions(getSessionsByEndpoint(endpoint));
  }, [endpoint, initialMode, lockMode, sessionParam]);

  useEffect(() => {
    if (runs.length === 0) return;
    const now = new Date().toISOString();
    const saved = getSession(sessionId);
    const session: StoredChatSession = {
      id: sessionId,
      endpoint,
      title: titleFromRuns(runs),
      route: pathname,
      mode,
      retrieval,
      strictness,
      createdAt: saved?.createdAt || now,
      updatedAt: now,
      runs: runs.slice(0, 12)
    };
    saveSession(session);
    setRecentSessions(getSessionsByEndpoint(endpoint));
  }, [endpoint, mode, pathname, retrieval, runs, sessionId, strictness]);

  const startNewChat = () => {
    setRuns([]);
    setQuestion("");
    setSessionId(makeSessionId());
    setRecentSessions(getSessionsByEndpoint(endpoint));
    if (sessionParam) {
      router.replace(pathname);
    }
  };

  const request = useMemo<ChatRequest>(
    () => ({
      question,
      mode,
      retrieval_level: retrieval,
      evidence_strictness: strictness,
      language: "zh",
      filters: {
        year_from: 2020,
        study_type: [],
        open_access_only: false
      },
      conversation_history: conversationHistory
    }),
    [conversationHistory, mode, question, retrieval, strictness]
  );

  return (
    <div className="min-h-[calc(100vh-97px)] overflow-x-auto bg-[#eef2ef] lg:min-h-screen">
      <div className="grid min-h-[calc(100vh-97px)] min-w-[1160px] grid-cols-[282px_minmax(500px,1fr)_360px] lg:min-h-screen">
        <aside className="border-r border-[#d5ddd8] bg-[#fbfcfb]">
          <div className="flex h-full flex-col">
            <div className="border-b border-[#e1e7e4] p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase text-[#687782]">Workspace</p>
                  <h2 className="mt-1 text-lg font-black text-ink">{workspaceTitle}</h2>
                </div>
                <button
                  className="focus-ring grid h-10 w-10 place-items-center rounded-md border border-[#d5ddd8] bg-white text-[#176b5c] hover:bg-[#eef4f1]"
                  onClick={startNewChat}
                  title="New chat"
                  type="button"
                >
                  <MessageSquarePlus size={18} />
                </button>
              </div>
            </div>

            <div className="flex-1 space-y-6 overflow-y-auto p-5">
              <ControlGroup icon={<Network size={16} />} title="Route">
                {lockMode ? (
                  <LockedRoute mode={mode} />
                ) : (
                  <Segmented
                    options={[
                      ["auto", "Auto"],
                      ["medical_rag", "Medical"],
                      ["web_search", "Web"],
                      ["hybrid", "Hybrid"]
                    ]}
                    value={mode}
                    onChange={(value) => setMode(value as AgentMode)}
                  />
                )}
              </ControlGroup>

              <ControlGroup icon={<Layers3 size={16} />} title="Retrieval">
                <Segmented
                  options={[
                    ["basic", "Base"],
                    ["advanced", "Advanced"]
                  ]}
                  value={retrieval}
                  onChange={(value) => setRetrieval(value as RetrievalLevel)}
                />
              </ControlGroup>

              <ControlGroup icon={<ShieldCheck size={16} />} title="Strictness">
                <Segmented
                  options={[
                    ["low", "Low"],
                    ["medium", "Medium"],
                    ["high", "High"]
                  ]}
                  value={strictness}
                  onChange={(value) => setStrictness(value as EvidenceStrictness)}
                />
              </ControlGroup>

              <div className="border-t border-[#e1e7e4] pt-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase text-[#687782]">
                  <MessagesSquare size={15} />
                  Recent Conversations
                </div>
                <RecentSessions
                  currentSessionId={runs.length ? sessionId : undefined}
                  endpoint={endpoint}
                  pathname={pathname}
                  sessions={recentSessions}
                />
              </div>

              <div className="border-t border-[#e1e7e4] pt-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase text-[#687782]">
                  <Search size={15} />
                  Prompt Starters
                </div>
                <div className="space-y-2">
                  {examples.map((item) => (
                    <button
                      key={item}
                      className="focus-ring block w-full rounded-md border border-[#dce4e0] bg-white px-3 py-3 text-left text-sm leading-5 text-[#263844] transition hover:border-[#aecfc1] hover:bg-[#f8fbf9]"
                      onClick={() => setQuestion(item)}
                      type="button"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>

              <div className="border-t border-[#e1e7e4] pt-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase text-[#687782]">
                  <SlidersHorizontal size={15} />
                  Run State
                </div>
                <RunState active={visibleResponse} isPending={mutation.isPending} pendingQuestion={pendingQuestion} />
              </div>

              <div className="border-t border-[#e1e7e4] pt-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase text-[#687782]">
                  <Activity size={15} />
                  Route Flow
                </div>
                <RouteFlow steps={plannedSteps} response={visibleResponse} isPending={mutation.isPending} />
              </div>
            </div>
          </div>
        </aside>

        <main className="flex min-h-[calc(100vh-97px)] flex-col lg:min-h-screen">
          <header className="border-b border-[#d5ddd8] bg-[#fbfcfb]/95 px-5 py-4 backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <div className="grid h-9 w-9 place-items-center rounded-md bg-[#176b5c] text-white">
                    <FileSearch size={18} />
                  </div>
                  <div>
                    <h1 className="text-xl font-black text-ink">{title}</h1>
                    <p className="text-xs font-semibold text-[#687782]">
                      Trace ID: {visibleResponse?.trace_id || (mutation.isPending ? "running" : "not started")}
                    </p>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={visibleResponse?.confidence || "neutral"}>
                  {mutation.isPending ? "running" : visibleResponse?.confidence || "ready"}
                </Badge>
                <Badge>{visibleResponse ? `${visibleResponse.evidence.length} sources` : "0 sources"}</Badge>
                <Badge>{mode}</Badge>
              </div>
            </div>
          </header>

          <div className="flex-1 overflow-y-auto px-5 py-5">
            {mutation.error ? (
              <div className="mb-4 rounded-md border border-[#e9a38f] bg-[#fff3ee] p-4 text-sm text-[#95402a]">
                {mutation.error.message}
              </div>
            ) : null}

            {runs.length > 0 || mutation.isPending ? (
              <ChatThread
                runs={runs}
                pendingQuestion={pendingQuestion}
                plannedSteps={plannedSteps}
                answerOnly={answerOnly}
              />
            ) : (
              <EmptyState steps={plannedSteps} answerOnly={answerOnly} />
            )}
          </div>

          <form
            className="border-t border-[#d5ddd8] bg-[#fbfcfb] p-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (canSubmit) mutation.mutate(request);
            }}
          >
            <div className="mx-auto flex max-w-5xl gap-3">
              <textarea
                className="focus-ring min-h-24 flex-1 resize-none rounded-md border border-[#cbd7d2] bg-white p-4 text-sm leading-6 text-ink shadow-[0_1px_2px_rgba(20,33,61,0.04)]"
                placeholder="Ask a follow-up or start a new web/literature question..."
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <Button className="h-24 w-24 shrink-0" disabled={!canSubmit}>
                {mutation.isPending ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
                Run
              </Button>
            </div>
          </form>
        </main>

        <aside className="border-l border-[#d5ddd8] bg-[#f6f8f7]">
          <EvidencePanel
            response={visibleResponse}
            title={panelTitle}
            isPending={mutation.isPending}
            pendingQuestion={pendingQuestion}
          />
        </aside>
      </div>
    </div>
  );
}

function RecentSessions({
  currentSessionId,
  endpoint,
  pathname,
  sessions
}: {
  currentSessionId?: string;
  endpoint: ChatEndpoint;
  pathname: string;
  sessions: StoredChatSession[];
}) {
  const visible = sessions.slice(0, 5);
  return (
    <div className="space-y-2">
      {visible.length ? (
        visible.map((session) => (
          <Link
            key={session.id}
            className={cn(
              "focus-ring block rounded-md border border-[#dce4e0] bg-white px-3 py-3 text-left transition hover:border-[#aecfc1] hover:bg-[#f8fbf9]",
              currentSessionId === session.id && "border-[#b9d8ca] bg-[#e2f1eb]"
            )}
            href={`${pathname}?session=${session.id}`}
          >
            <span className="block truncate text-sm font-black text-[#263844]">{session.title}</span>
            {session.runs[0]?.question && session.runs[0].question !== session.title ? (
              <span className="mt-1 block line-clamp-2 text-xs font-semibold leading-5 text-[#52636d]">
                Latest: {session.runs[0].question}
              </span>
            ) : null}
            <span className="mt-1 block text-xs font-semibold text-[#687782]">
              {session.runs.length} turns · {formatShortDate(session.updatedAt)}
            </span>
          </Link>
        ))
      ) : (
        <div className="rounded-md border border-dashed border-[#cdd8d3] bg-white px-3 py-3 text-sm font-semibold text-[#687782]">
          No saved conversations yet.
        </div>
      )}
      <Link
        className="focus-ring block rounded-md border border-[#cbd7d2] bg-[#f8fbf9] px-3 py-2 text-center text-xs font-black uppercase text-[#176b5c] hover:bg-white"
        href={`/history?type=${endpoint}`}
      >
        Open history
      </Link>
    </div>
  );
}

function ChatThread({
  runs,
  pendingQuestion,
  plannedSteps,
  answerOnly
}: {
  runs: ConversationRun[];
  pendingQuestion?: string;
  plannedSteps: string[];
  answerOnly: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const orderedRuns = useMemo(() => runs.slice().reverse(), [runs]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [runs.length, pendingQuestion]);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {orderedRuns.map((run, index) => (
        <ConversationRunView
          key={run.response.trace_id}
          run={run}
          isLatest={index === orderedRuns.length - 1}
          plannedSteps={plannedSteps}
          answerOnly={answerOnly}
        />
      ))}

      {pendingQuestion ? (
        <section className="space-y-3">
          <UserQuestionBubble question={pendingQuestion} />
          <div className="rounded-md border border-[#d8dfdc] bg-[#fbfcfb] p-5 shadow-[0_10px_24px_rgba(20,33,61,0.06)]">
            <div className="flex items-center gap-3 text-sm font-black text-[#176b5c]">
              <Loader2 className="animate-spin" size={18} />
              Searching, extracting evidence, and preparing the final answer...
            </div>
            <div className="mt-4">
              <AgentTimeline plannedSteps={plannedSteps} />
            </div>
          </div>
        </section>
      ) : null}
      <div ref={bottomRef} />
    </div>
  );
}

function ConversationRunView({
  run,
  isLatest,
  plannedSteps,
  answerOnly
}: {
  run: ConversationRun;
  isLatest: boolean;
  plannedSteps: string[];
  answerOnly: boolean;
}) {
  return (
    <section className="space-y-3">
      <UserQuestionBubble question={run.question} />
      <AssistantAnswerBubble
        response={run.response}
        isLatest={isLatest}
        plannedSteps={plannedSteps}
        answerOnly={answerOnly}
      />
    </section>
  );
}

function UserQuestionBubble({ question }: { question: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%] rounded-md bg-[#176b5c] px-4 py-3 text-sm font-semibold leading-6 text-white shadow-[0_8px_18px_rgba(23,107,92,0.18)]">
        {question}
      </div>
    </div>
  );
}

function AssistantAnswerBubble({
  response,
  isLatest,
  plannedSteps,
  answerOnly
}: {
  response: ChatResponse;
  isLatest: boolean;
  plannedSteps: string[];
  answerOnly: boolean;
}) {
  return (
    <div className="rounded-md border border-[#d8dfdc] bg-[#fbfcfb] p-5 shadow-[0_10px_24px_rgba(20,33,61,0.06)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-[#e5ebe8] pb-4">
        <div>
          <p className="text-xs font-black uppercase text-[#687782]">
            {isLatest ? "Final Answer" : "Previous Answer"}
          </p>
          <h2 className="mt-1 text-base font-black text-ink">{response.route_decision.query_type}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={response.confidence}>{response.confidence}</Badge>
          <Badge>{response.evidence.length} sources</Badge>
          <Badge>{response.latency_ms} ms</Badge>
        </div>
      </div>
      <div className="whitespace-pre-wrap text-sm leading-7 text-[#263844]">{response.answer}</div>

      {isLatest && !answerOnly ? (
        <div className="mt-5 border-t border-[#e5ebe8] pt-5">
          <AnswerDiagnostics response={response} plannedSteps={plannedSteps} />
        </div>
      ) : null}
    </div>
  );
}

function buildConversationHistory(runs: ConversationRun[]): ConversationTurn[] {
  return runs
    .slice(0, 6)
    .reverse()
    .map(({ question, response }) => ({
      question,
      answer: response.answer.slice(0, 1200),
      route: response.route,
      confidence: response.confidence,
      evidence_titles: response.evidence.slice(0, 6).map((item) => item.title)
    }));
}

function AnswerDiagnostics({
  response,
  plannedSteps
}: {
  response: ChatResponse;
  plannedSteps: string[];
}) {
  return (
      <section className="grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(300px,0.75fr)]">
        <div className="rounded-md border border-[#d8dfdc] bg-[#fbfcfb] p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-black text-ink">
              <Gauge size={18} />
              Evidence Gate
            </div>
            <Badge tone={response.confidence}>{Math.round(response.confidence_score * 100)}%</Badge>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[#e4ebe7]">
            <div
              className="h-full rounded-full bg-[#176b5c]"
              style={{ width: `${Math.min(Math.max(response.confidence_score * 100, 4), 100)}%` }}
            />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <MetricPill icon={<BookOpenCheck size={16} />} label="Sources" value={String(response.evidence.length)} />
            <MetricPill icon={<Clock3 size={16} />} label="Latency" value={`${response.latency_ms}ms`} />
            <MetricPill icon={<Activity size={16} />} label="Route" value={response.route} />
          </div>
        </div>

        <div className="rounded-md border border-[#d8dfdc] bg-[#fbfcfb] p-5">
          <div className="mb-4 flex items-center gap-2 text-sm font-black text-ink">
            <Activity size={18} />
            Agent Step Timeline
          </div>
          <AgentTimeline response={response} plannedSteps={plannedSteps} />
        </div>
      </section>
  );
}

function EvidencePanel({
  response,
  title,
  isPending,
  pendingQuestion
}: {
  response?: ChatResponse;
  title: string;
  isPending: boolean;
  pendingQuestion?: string;
}) {
  return (
    <div className="flex h-full min-h-[520px] flex-col">
      <div className="border-b border-[#d5ddd8] bg-[#fbfcfb] p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-black uppercase text-[#687782]">Evidence</p>
            <h2 className="mt-1 text-lg font-black text-ink">{title}</h2>
          </div>
          <Badge tone={response?.confidence || "neutral"}>{isPending ? "running" : response ? response.confidence : "empty"}</Badge>
        </div>
        {isPending ? (
          <div className="mt-4 rounded-md border border-[#cfe0d8] bg-[#eef8f3] p-3">
            <div className="flex items-center gap-2 text-sm font-black text-[#176b5c]">
              <Loader2 className="animate-spin" size={15} />
              Collecting fresh evidence
            </div>
            {pendingQuestion ? (
              <p className="mt-2 line-clamp-2 text-xs font-semibold leading-5 text-[#52636d]">{pendingQuestion}</p>
            ) : null}
          </div>
        ) : response ? (
          <div className="mt-4 grid grid-cols-3 gap-2">
            <PanelStat label="Items" value={String(response.evidence.length)} />
            <PanelStat label="Score" value={`${Math.round(response.confidence_score * 100)}%`} />
            <PanelStat label="Gate" value="Weighted" />
          </div>
        ) : null}
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {isPending ? <EvidencePendingList /> : null}
        {!isPending && response?.evidence.map((item, index) => (
          <EvidenceCard key={`${item.id}-${index}`} item={item} index={index + 1} />
        ))}
        {!isPending && !response ? (
          <div className="rounded-md border border-dashed border-[#cdd8d3] bg-[#fbfcfb] p-6 text-sm font-semibold text-[#687782]">
            No evidence selected.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function EvidencePendingList() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((item) => (
        <div key={item} className="rounded-md border border-[#dce4e0] bg-[#fbfcfb] p-4">
          <div className="h-3 w-20 animate-pulse rounded-full bg-[#dfe8e4]" />
          <div className="mt-4 h-4 w-4/5 animate-pulse rounded-full bg-[#dfe8e4]" />
          <div className="mt-2 h-4 w-2/3 animate-pulse rounded-full bg-[#e8eeee]" />
          <div className="mt-4 grid grid-cols-3 gap-2">
            <div className="h-9 animate-pulse rounded-md bg-[#edf3f0]" />
            <div className="h-9 animate-pulse rounded-md bg-[#edf3f0]" />
            <div className="h-9 animate-pulse rounded-md bg-[#edf3f0]" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ steps, answerOnly }: { steps: string[]; answerOnly: boolean }) {
  return (
    <div className="grid min-h-[280px] place-items-center md:min-h-[360px] xl:min-h-[520px]">
      <div className="w-full max-w-xl rounded-md border border-dashed border-[#cdd8d3] bg-[#fbfcfb] p-7">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-md bg-[#eef4f1] text-[#176b5c]">
          <ShieldCheck size={24} />
        </div>
        <h2 className="mt-5 text-center text-2xl font-black text-ink">{answerOnly ? "Final Answer Pending" : "Ready"}</h2>
        <div className="mt-5">
          <AgentTimeline plannedSteps={steps} />
        </div>
      </div>
    </div>
  );
}

function AgentTimeline({
  response,
  plannedSteps
}: {
  response?: ChatResponse;
  plannedSteps: string[];
}) {
  const rows = response
    ? response.trace.map((step) => ({
        title: step.name.replaceAll("_", " "),
        detail: step.detail,
        status: step.status
      }))
    : plannedSteps.map((step) => ({
        title: step,
        detail: "Pending",
        status: "skipped" as const
      }));

  return (
    <ol className="space-y-3">
      {rows.map((step, index) => (
        <li key={`${step.title}-${index}`} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
          <span
            className={cn(
              "grid h-6 w-6 place-items-center rounded-md text-xs font-black",
              step.status === "warning"
                ? "bg-[#fff2cd] text-[#7b5414]"
                : step.status === "error"
                  ? "bg-[#fde4d9] text-[#95402a]"
                  : "bg-[#eef4f1] text-[#176b5c]"
            )}
          >
            {index + 1}
          </span>
          <span>
            <span className="block text-xs font-black uppercase text-[#687782]">{step.title}</span>
            <span className="block text-sm leading-6 text-[#33444d]">{step.detail}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function RunState({
  active,
  isPending,
  pendingQuestion
}: {
  active?: ChatResponse;
  isPending: boolean;
  pendingQuestion?: string;
}) {
  return (
    <div className="grid gap-2">
      <RunRow label="Status" value={isPending ? "running" : active ? active.confidence : "idle"} />
      <RunRow label="Route" value={active?.route || "pending"} />
      <RunRow label="Latency" value={active ? `${active.latency_ms} ms` : "n/a"} />
      {isPending && pendingQuestion ? <RunNote label="Question" value={pendingQuestion} /> : null}
    </div>
  );
}

function RunRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex h-10 items-center justify-between rounded-md border border-[#dce4e0] bg-white px-3 text-sm">
      <span className="font-semibold text-[#687782]">{label}</span>
      <span className="font-black text-ink">{value}</span>
    </div>
  );
}

function RunNote({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#dce4e0] bg-white px-3 py-3 text-sm">
      <span className="block text-xs font-black uppercase text-[#687782]">{label}</span>
      <span className="mt-1 line-clamp-3 block font-semibold leading-5 text-[#263844]">{value}</span>
    </div>
  );
}

function LockedRoute({ mode }: { mode: AgentMode }) {
  const label = {
    auto: "Auto Router",
    medical_rag: "Medical RAG only",
    web_search: "Live Web Search only",
    hybrid: "Hybrid"
  }[mode];

  return (
    <div className="rounded-md border border-[#b9d8ca] bg-[#e2f1eb] px-3 py-3 text-sm font-black text-[#176b5c]">
      {label}
    </div>
  );
}

function formatShortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "saved";
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function RouteFlow({
  steps,
  response,
  isPending
}: {
  steps: string[];
  response?: ChatResponse;
  isPending: boolean;
}) {
  const rows = response
    ? response.trace.map((step) => ({
        title: step.name.replaceAll("_", " "),
        detail: step.status,
        status: step.status
      }))
    : steps.map((step, index) => ({
        title: step,
        detail: isPending && index === 0 ? "running" : "pending",
        status: isPending && index === 0 ? "running" : "pending"
      }));

  return (
    <ol className="space-y-2">
      {rows.map((step, index) => (
        <li
          key={`${step.title}-${index}`}
          className={cn(
            "flex gap-2 rounded-md border p-2",
            step.status === "ok"
              ? "border-[#b9d8ca] bg-[#f4faf7]"
              : step.status === "warning"
                ? "border-[#f1d28f] bg-[#fff8e6]"
                : step.status === "running"
                  ? "border-[#a9cfe0] bg-[#eef8fc]"
                  : "border-[#dce4e0] bg-white"
          )}
        >
          <span
            className={cn(
              "grid h-6 w-6 shrink-0 place-items-center rounded-md text-xs font-black",
              step.status === "warning"
                ? "bg-[#fff2cd] text-[#7b5414]"
                : step.status === "running"
                  ? "bg-[#dff1f8] text-[#285c72]"
                  : "bg-[#eef4f1] text-[#176b5c]"
            )}
          >
            {index + 1}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-bold leading-5 text-[#33444d]">{step.title}</span>
            <span className="block text-[10px] font-black uppercase text-[#687782]">{step.detail}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function ControlGroup({
  icon,
  title,
  children
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-black uppercase text-[#687782]">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}

function Segmented({
  options,
  value,
  onChange
}: {
  options: [string, string][];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div
      className="grid gap-1 rounded-md border border-[#d5ddd8] bg-[#edf2ef] p-1"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map(([key, label]) => (
        <button
          key={key}
          className={cn(
            "focus-ring h-9 rounded-md text-xs font-black text-[#687782] transition",
            key === value && "bg-white text-[#176b5c] shadow-sm"
          )}
          onClick={() => onChange(key)}
          type="button"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function MetricPill({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#e1e7e4] bg-[#f7faf8] p-3">
      <div className="flex items-center gap-2 text-xs font-black uppercase text-[#687782]">
        {icon}
        {label}
      </div>
      <div className="mt-2 truncate text-sm font-black text-ink">{value}</div>
    </div>
  );
}

function PanelStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#e1e7e4] bg-[#f7faf8] p-2">
      <div className="text-[10px] font-black uppercase text-[#687782]">{label}</div>
      <div className="mt-1 truncate text-sm font-black text-ink">{value}</div>
    </div>
  );
}
