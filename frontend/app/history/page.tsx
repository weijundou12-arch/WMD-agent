"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Clock3, ExternalLink, MessageSquareText, Search, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  deleteSession,
  endpointLabel,
  endpointRoute,
  getAllSessions,
  type ChatEndpoint,
  type StoredChatSession
} from "@/lib/chat-history";

const filters: Array<[ChatEndpoint | "all", string]> = [
  ["all", "All"],
  ["web", "Web Search"],
  ["medical", "Medical RAG"],
  ["chat", "Agent"]
];

export default function HistoryPage() {
  return (
    <Suspense fallback={null}>
      <HistoryPageContent />
    </Suspense>
  );
}

function HistoryPageContent() {
  const searchParams = useSearchParams();
  const initialType = (searchParams.get("type") || "all") as ChatEndpoint | "all";
  const [type, setType] = useState<ChatEndpoint | "all">(filters.some(([value]) => value === initialType) ? initialType : "all");
  const [sessions, setSessions] = useState<StoredChatSession[]>([]);

  useEffect(() => {
    setSessions(getAllSessions());
  }, []);

  const visible = useMemo(
    () => sessions.filter((session) => type === "all" || session.endpoint === type),
    [sessions, type]
  );

  const removeSession = (id: string) => {
    deleteSession(id);
    setSessions(getAllSessions());
  };

  return (
    <div className="min-h-screen bg-[#eef2ef] px-5 py-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase text-[#687782]">Conversation Library</p>
            <h1 className="mt-1 text-3xl font-black text-ink">History</h1>
          </div>
          <div className="flex rounded-md border border-[#d5ddd8] bg-[#fbfcfb] p-1">
            {filters.map(([value, label]) => (
              <button
                key={value}
                className={cn(
                  "focus-ring h-9 rounded-md px-3 text-xs font-black text-[#687782] transition",
                  type === value && "bg-[#176b5c] text-white"
                )}
                onClick={() => setType(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        </header>

        {visible.length ? (
          <div className="grid gap-3">
            {visible.map((session) => (
              <article
                key={session.id}
                className="rounded-md border border-[#d8dfdc] bg-[#fbfcfb] p-5 shadow-[0_10px_24px_rgba(20,33,61,0.05)]"
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge>{endpointLabel(session.endpoint)}</Badge>
                      <Badge>{session.runs.length} turns</Badge>
                      <Badge>{session.retrieval}</Badge>
                    </div>
                    <h2 className="truncate text-lg font-black text-ink">{session.title}</h2>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-[#52636d]">
                      {session.runs[0]?.response.answer || session.runs[0]?.question || "Saved conversation"}
                    </p>
                    <div className="mt-3 flex items-center gap-2 text-xs font-semibold text-[#687782]">
                      <Clock3 size={14} />
                      Updated {formatDate(session.updatedAt)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Link
                      className="focus-ring inline-flex h-10 items-center gap-2 rounded-md bg-[#176b5c] px-3 text-sm font-black text-white"
                      href={`${endpointRoute(session.endpoint)}?session=${session.id}`}
                    >
                      <ExternalLink size={16} />
                      Open
                    </Link>
                    <button
                      className="focus-ring grid h-10 w-10 place-items-center rounded-md border border-[#e2ccc5] bg-[#fff6f3] text-[#95402a]"
                      onClick={() => removeSession(session.id)}
                      title="Delete session"
                      type="button"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="grid min-h-[360px] place-items-center rounded-md border border-dashed border-[#cdd8d3] bg-[#fbfcfb]">
            <div className="text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-md bg-[#eef4f1] text-[#176b5c]">
                <MessageSquareText size={22} />
              </div>
              <h2 className="mt-4 text-xl font-black text-ink">No saved conversations</h2>
              <p className="mt-2 text-sm font-semibold text-[#687782]">
                Run a Web Search or Medical RAG question, then return here to reopen it.
              </p>
              <Link
                className="focus-ring mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-[#176b5c] px-4 text-sm font-black text-white"
                href="/web-search"
              >
                <Search size={16} />
                Start Web Search
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}
