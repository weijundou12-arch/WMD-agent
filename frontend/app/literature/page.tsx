"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { BookOpen, Loader2, Plus, Search } from "lucide-react";
import { searchPapers } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function LiteraturePage() {
  const [query, setQuery] = useState("semaglutide bone mineral density");
  const mutation = useMutation({ mutationFn: searchPapers });
  const papers = mutation.data?.results || [];

  return (
    <div className="min-h-screen p-5">
      <div className="mx-auto max-w-6xl">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-black text-ink">Literature Search</h1>
            <p className="text-sm text-[#60717c]">Search PubMed / Europe PMC metadata and import records into the evidence library.</p>
          </div>
          <Badge>{papers.length} records</Badge>
        </div>

        <form
          className="mb-5 flex gap-3 rounded-md border border-[#d9e0dd] bg-white p-3 shadow-panel"
          onSubmit={(event) => {
            event.preventDefault();
            if (query.trim()) mutation.mutate(query);
          }}
        >
          <div className="grid h-10 w-10 place-items-center rounded-md bg-[#e2f1eb] text-pine">
            <Search size={18} />
          </div>
          <input
            className="focus-ring min-w-0 flex-1 rounded-md border border-[#cad7d2] px-3 text-sm"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Button disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 className="animate-spin" size={17} /> : <Search size={17} />}
            Search
          </Button>
        </form>

        {mutation.error ? (
          <div className="mb-4 rounded-md border border-[#e8a58f] bg-[#fff3ee] p-4 text-sm text-[#95402a]">
            {mutation.error.message}
          </div>
        ) : null}

        <div className="grid gap-4">
          {papers.map((paper) => (
            <article key={paper.id} className="rounded-md border border-[#d9e0dd] bg-white p-5 shadow-panel">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-black leading-6 text-ink">{paper.title}</h2>
                  <p className="mt-1 text-sm text-[#60717c]">
                    {paper.authors.slice(0, 4).join(", ") || "Unknown authors"} · {paper.journal || "Unknown journal"} · {paper.publication_year || "n/a"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {paper.is_open_access ? <Badge tone="strong">Open Access</Badge> : null}
                  <Badge>{paper.publication_type || "article"}</Badge>
                </div>
              </div>
              <p className="line-clamp-4 text-sm leading-6 text-[#334155]">{paper.abstract || "No abstract available."}</p>
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[#52616b]">
                <Badge>PMID {paper.pmid || "n/a"}</Badge>
                <Badge>DOI {paper.doi || "n/a"}</Badge>
                <Button variant="secondary" className="h-9">
                  <Plus size={15} />
                  Add to RAG
                </Button>
                <Button variant="ghost" className="h-9">
                  <BookOpen size={15} />
                  View Evidence
                </Button>
              </div>
            </article>
          ))}
          {!papers.length ? (
            <div className="rounded-md border border-[#d9e0dd] bg-white p-8 text-center text-sm text-[#60717c]">
              Run a search to view paper cards.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
