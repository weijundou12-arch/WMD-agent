"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BarChart3, Clock, DollarSign, ShieldCheck } from "lucide-react";
import { listEvalRuns, runEvaluation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const metricCards = [
  ["retrieval recall@k", "Evidence recall against curated relevance sets"],
  ["MRR / nDCG", "Whether relevant papers rank near the top"],
  ["faithfulness", "Whether answer claims are supported by evidence"],
  ["citation precision", "Whether each citation supports the sentence"],
  ["answer relevancy", "Whether the answer addresses the question"],
  ["hallucination rate", "Unsupported content rate"],
  ["latency", "End-to-end response time"],
  ["cost", "Search and model API cost"]
];

export default function EvaluationPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["eval-runs"], queryFn: listEvalRuns });
  const mutation = useMutation({
    mutationFn: runEvaluation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["eval-runs"] })
  });
  const latest = data?.results?.[0];

  return (
    <div className="min-h-screen p-5">
      <div className="mx-auto max-w-7xl">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-black text-ink">Evaluation Dashboard</h1>
            <p className="text-sm text-[#60717c]">Trace-derived MVP metrics with slots for RAGAS and DeepEval.</p>
          </div>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            <BarChart3 size={17} />
            Run Evaluation
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Metric icon={<ShieldCheck size={18} />} label="Faithfulness" value={latest?.faithfulness ?? 0} />
          <Metric icon={<Activity size={18} />} label="Citation Precision" value={latest?.citation_precision ?? 0} />
          <Metric icon={<BarChart3 size={18} />} label="Answer Relevancy" value={latest?.answer_relevancy ?? 0} />
          <Metric icon={<Clock size={18} />} label="Mean Latency" value={`${latest?.mean_latency_ms ?? 0} ms`} raw />
        </div>

        <section className="mt-5 rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
          <div className="mb-4 flex items-center gap-2 text-sm font-black text-ink">
            <DollarSign size={17} />
            Metrics Catalog
          </div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {metricCards.map(([label, text]) => (
              <div key={label} className="rounded-md border border-[#d9e0dd] bg-[#f7faf8] p-4">
                <div className="text-sm font-black text-ink">{label}</div>
                <p className="mt-2 text-sm leading-6 text-[#52616b]">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-5 rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
          <h2 className="mb-3 text-base font-black text-ink">Recent Evaluation Runs</h2>
          <div className="space-y-3">
            {(data?.results || []).map((run) => (
              <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#d9e0dd] p-3">
                <div>
                  <div className="font-bold text-ink">{run.id}</div>
                  <div className="text-xs text-[#60717c]">{new Date(run.created_at).toLocaleString()}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge>{run.total_runs} runs</Badge>
                  <Badge tone="strong">faithfulness {run.faithfulness}</Badge>
                  <Badge>latency {run.mean_latency_ms} ms</Badge>
                </div>
              </div>
            ))}
            {!data?.results?.length ? <p className="text-sm text-[#60717c]">No evaluation runs yet.</p> : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
  raw = false
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  raw?: boolean;
}) {
  const display = raw || typeof value === "string" ? value : `${Math.round(value * 100)}%`;
  return (
    <div className="rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-[#e2f1eb] text-pine">{icon}</div>
      <div className="text-xs font-black uppercase text-[#60717c]">{label}</div>
      <div className="mt-2 text-2xl font-black text-ink">{display}</div>
    </div>
  );
}
