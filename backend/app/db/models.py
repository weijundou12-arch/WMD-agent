from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return uuid4().hex


class PaperModel(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    pmid: Mapped[str | None] = mapped_column(String(64), index=True)
    pmcid: Mapped[str | None] = mapped_column(String(64), index=True)
    doi: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text, default="")
    journal: Mapped[str | None] = mapped_column(String(255))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    mesh_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    publication_type: Mapped[str | None] = mapped_column(String(255))
    is_open_access: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(64), default="pubmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="paper")


class ChunkModel(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), index=True)
    section: Mapped[str | None] = mapped_column(String(128))
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    contextual_header: Mapped[str | None] = mapped_column(Text)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    paper: Mapped[PaperModel] = relationship(back_populates="chunks")


class QARunModel(Base):
    __tablename__ = "qa_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_question: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(String(64), index=True)
    retrieval_level: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    evidence: Mapped[list["EvidenceModel"]] = relationship(back_populates="qa_run")


class EvidenceModel(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    qa_run_id: Mapped[str] = mapped_column(ForeignKey("qa_runs.id"), index=True)
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id"), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("chunks.id"), nullable=True)
    snippet: Mapped[str] = mapped_column(Text)
    support_level: Mapped[str] = mapped_column(String(64))
    retrieval_score: Mapped[float] = mapped_column(Float)
    rerank_score: Mapped[float] = mapped_column(Float)

    qa_run: Mapped[QARunModel] = relationship(back_populates="evidence")
