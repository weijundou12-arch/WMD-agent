from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.chat import ChatResponse, EvalRun, Paper


class InMemoryStore:
    """Small development store used before wiring PostgreSQL persistence."""

    def __init__(self) -> None:
        self.papers: dict[str, Paper] = {}
        self.runs: dict[str, ChatResponse] = {}
        self.eval_runs: list[EvalRun] = []

    def add_paper(self, paper: Paper) -> Paper:
        self.papers[paper.id] = paper
        return paper

    def list_papers(self) -> list[Paper]:
        return sorted(self.papers.values(), key=lambda item: item.created_at, reverse=True)

    def get_paper(self, paper_id: str) -> Paper | None:
        return self.papers.get(paper_id)

    def add_run(self, response: ChatResponse) -> ChatResponse:
        self.runs[response.trace_id] = response
        for evidence in response.evidence:
            if evidence.source_type == "paper":
                self.papers.setdefault(
                    evidence.id,
                    Paper(
                        id=evidence.id,
                        pmid=evidence.pmid,
                        pmcid=evidence.pmcid,
                        doi=evidence.doi,
                        title=evidence.title,
                        abstract=evidence.snippet,
                        journal=evidence.journal,
                        publication_year=evidence.year,
                        publication_type=evidence.study_type,
                        source="answer_evidence",
                        url=evidence.url,
                    ),
                )
        return response

    def get_run(self, run_id: str) -> ChatResponse | None:
        return self.runs.get(run_id)

    def list_runs(self) -> list[ChatResponse]:
        return list(self.runs.values())

    def add_eval_run(self, run: EvalRun) -> EvalRun:
        self.eval_runs.insert(0, run)
        return run

    def list_eval_runs(self) -> list[EvalRun]:
        return self.eval_runs


store = InMemoryStore()


def new_trace_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_utc() -> datetime:
    return datetime.now(UTC)
