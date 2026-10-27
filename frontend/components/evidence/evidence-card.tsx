import { ExternalLink, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { EvidenceItem } from "@/lib/types";

export function EvidenceCard({ item, index }: { item: EvidenceItem; index: number }) {
  const score = Math.round(item.rerank_score * 100);
  const retrieval = Math.round(item.retrieval_score * 100);
  const quality = Math.round(item.source_quality_score * 100);
  const sourceLabel = item.pmid ? `PMID ${item.pmid}` : item.doi ? `DOI ${item.doi}` : item.source_type;
  return (
    <article className="rounded-md border border-[#d8dfdc] bg-[#fbfcfb] p-4 shadow-[0_1px_2px_rgba(20,33,61,0.04)]">
      <div className="mb-3 flex items-start gap-3">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-[#eef4f1] text-xs font-black text-[#176b5c]">
          {index}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={item.support_level === "direct" ? "strong" : "neutral"}>{item.support_level}</Badge>
            <span className="text-xs font-bold text-[#687782]">Rerank {score}%</span>
          </div>
          <h3 className="mt-2 text-sm font-black leading-5 text-ink">{item.title}</h3>
        </div>
      </div>
      <p className="max-h-44 overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-[#f5f8f6] p-3 text-sm leading-6 text-[#32424b]">
        {item.snippet}
      </p>
      <div className="mt-3 grid gap-2 text-xs text-[#52616b]">
        <div className="flex items-center gap-2">
          <FileText size={13} />
          <span className="truncate">{sourceLabel}</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <span className="truncate">{item.journal || item.source_type}</span>
          <span>{item.year || "year n/a"}</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <MiniScore label="Retrieval" value={`${retrieval}%`} />
          <MiniScore label="Rerank" value={`${score}%`} />
          <MiniScore label="Quality" value={`${quality}%`} />
        </div>
        {item.study_type ? <div className="truncate font-semibold text-[#687782]">{item.study_type}</div> : null}
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-[#e6ebe8] pt-3 text-xs">
        <span className="font-semibold text-[#176b5c]">{item.section || "Evidence snippet"}</span>
        {item.url ? (
          <a className="inline-flex items-center gap-1 font-semibold text-ink hover:text-[#176b5c]" href={item.url} target="_blank">
            Source <ExternalLink size={13} />
          </a>
        ) : null}
      </div>
    </article>
  );
}

function MiniScore({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-md border border-[#e1e7e4] bg-[#f7faf8] px-2 py-1">
      <span className="block text-[9px] font-black uppercase text-[#7a8991]">{label}</span>
      <span className="font-black text-[#263844]">{value}</span>
    </span>
  );
}
