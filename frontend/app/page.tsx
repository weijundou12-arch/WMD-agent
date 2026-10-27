import Link from "next/link";
import { ArrowRight, BarChart3, BookOpen, SearchCheck } from "lucide-react";
import { buttonStyles } from "@/components/ui/button";

const features = [
  {
    icon: BookOpen,
    title: "Medical Literature RAG",
    text: "PubMed and Europe PMC metadata, abstract retrieval, confidence gating, and citation-first synthesis."
  },
  {
    icon: SearchCheck,
    title: "Evidence Web Search",
    text: "Brave or Tavily search, source credibility ranking, evidence snippets, and cited answers."
  },
  {
    icon: BarChart3,
    title: "Trace & Evaluation",
    text: "Run traces, confidence scores, evidence cards, latency, and evaluation metrics ready for RAGAS or DeepEval."
  }
];

export default function HomePage() {
  return (
    <div className="min-h-screen px-5 py-8">
      <section className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <div className="py-10">
          <div className="mb-4 inline-flex rounded-md border border-[#cad7d2] bg-white px-3 py-2 text-xs font-black uppercase text-pine">
            Evidence-first medical agent
          </div>
          <h1 className="max-w-3xl text-5xl font-black leading-tight text-ink md:text-6xl">
            WMD-agent
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-[#52616b]">
            Ask medical questions with literature-grounded and web-grounded evidence. The system routes,
            searches, filters, confidence-gates, and answers with traceable citations.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/chat" className={buttonStyles("primary")}>
              Open Web App <ArrowRight size={18} />
            </Link>
            <Link href="/evaluation" className={buttonStyles("secondary")}>
              View Dashboard
            </Link>
          </div>
        </div>

        <div className="rounded-md border border-[#d9e0dd] bg-white p-4 shadow-panel">
          <div className="grid gap-3">
            <div className="rounded-md bg-[#14213d] p-5 text-white">
              <div className="text-xs font-bold uppercase text-[#aee4d5]">Route</div>
              <div className="mt-2 text-2xl font-black">Hybrid: PubMed + Web</div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                <span className="rounded-md bg-white/12 p-2">Query Rewrite</span>
                <span className="rounded-md bg-white/12 p-2">Reranker</span>
                <span className="rounded-md bg-white/12 p-2">CRAG Gate</span>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <MiniMetric label="Confidence" value="0.78" />
              <MiniMetric label="Evidence" value="8" />
              <MiniMetric label="Latency" value="4.2s" />
              <MiniMetric label="Citations" value="PMID / DOI" />
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto mt-6 grid max-w-7xl gap-4 md:grid-cols-3">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <article key={feature.title} className="rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
              <Icon className="text-pine" size={24} />
              <h2 className="mt-4 text-lg font-black text-ink">{feature.title}</h2>
              <p className="mt-2 text-sm leading-6 text-[#52616b]">{feature.text}</p>
            </article>
          );
        })}
      </section>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[#d9e0dd] bg-[#f7faf8] p-4">
      <div className="text-xs font-black uppercase text-[#60717c]">{label}</div>
      <div className="mt-2 text-xl font-black text-ink">{value}</div>
    </div>
  );
}
