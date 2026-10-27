"use client";

import { useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { listPapers } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export default function EvidencePage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["papers"], queryFn: listPapers });
  const papers = data?.results || [];

  return (
    <div className="min-h-screen p-5">
      <div className="mx-auto max-w-6xl">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-black text-ink">Evidence Library</h1>
            <p className="text-sm text-[#60717c]">Local paper metadata and retrieved evidence records.</p>
          </div>
          <Badge>{papers.length} papers</Badge>
        </div>

        {error ? (
          <div className="rounded-md border border-[#e8a58f] bg-[#fff3ee] p-4 text-sm text-[#95402a]">{error.message}</div>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          {papers.map((paper) => (
            <article key={paper.id} className="rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-[#e2f1eb] text-pine">
                <Database size={18} />
              </div>
              <h2 className="text-base font-black leading-6 text-ink">{paper.title}</h2>
              <p className="mt-2 text-sm leading-6 text-[#52616b]">{paper.abstract || "No abstract stored."}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge>PMID {paper.pmid || "n/a"}</Badge>
                <Badge>{paper.publication_year || "year n/a"}</Badge>
                {paper.is_open_access ? <Badge tone="strong">OA</Badge> : null}
              </div>
            </article>
          ))}
        </div>

        {!papers.length && !isLoading ? (
          <div className="rounded-md border border-[#d9e0dd] bg-white p-8 text-center text-sm text-[#60717c]">
            Ask a question or search literature to populate this library.
          </div>
        ) : null}
        {isLoading ? <div className="text-sm text-[#60717c]">Loading...</div> : null}
      </div>
    </div>
  );
}
