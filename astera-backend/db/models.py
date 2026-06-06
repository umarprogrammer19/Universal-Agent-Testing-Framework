"""
db/models.py

SQLAlchemy ORM models for the Universal Agent Testing Framework.

Table relationships:
    TestSuite  ──< TestCase
    TestSuite  ──< Run
    Run        ──< Run          (self-referential: parent_run_id for multi-model children)
    Run        ──< TestResult
    TestCase   ──< TestResult
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# TestSuite
# ---------------------------------------------------------------------------

class TestSuite(Base):
    __tablename__ = "test_suites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    default_model_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── multi-model columns (new) ──────────────────────────────────────────
    multi_model_test: Mapped[bool] = mapped_column(Boolean, default=False)
    models_to_test: Mapped[list] = mapped_column(JSON, default=lambda: ["gemini"])

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    # relationships
    test_cases: Mapped[list[TestCase]] = relationship(
        "TestCase", back_populates="suite", cascade="all, delete-orphan"
    )
    runs: Mapped[list[Run]] = relationship(
        "Run", back_populates="suite", foreign_keys="Run.suite_id"
    )


# ---------------------------------------------------------------------------
# TestCase
# ---------------------------------------------------------------------------

class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    suite_id: Mapped[str] = mapped_column(
        String, ForeignKey("test_suites.id", ondelete="CASCADE"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Tool declarations passed to the adapter (list of dicts)
    tools: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Ordered list of tool names the model is expected to call
    expected_tools: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Optional hard-coded exact output for assertion checking
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ground-truth answer for LLM-as-judge scoring
    golden_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Max tool-call steps the agent is allowed to take
    max_steps: Mapped[int | None] = mapped_column(Integer, nullable=True, default=5)

    # Display/sort order within a suite
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    # relationships
    suite: Mapped[TestSuite] = relationship("TestSuite", back_populates="test_cases")
    results: Mapped[list[TestResult]] = relationship(
        "TestResult", back_populates="test_case", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    suite_id: Mapped[str] = mapped_column(
        String, ForeignKey("test_suites.id", ondelete="CASCADE"), nullable=False
    )

    # ── model identification ───────────────────────────────────────────────
    # For single-model runs: 'gemini' | 'gpt-4' | 'claude'
    # For the orchestrator record of a multi-model run: 'multi'
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ── multi-model support ────────────────────────────────────────────────
    multi_model_test: Mapped[bool] = mapped_column(Boolean, default=False)
    models_to_test: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Self-referential: child runs point back to their orchestrator
    parent_run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )

    # ── execution state ────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | running | completed | failed

    pass_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fail_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full flattened trace stored for the replay endpoint
    # (renamed from execution_trace → execution_trace_replay)
    execution_trace_replay: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # relationships
    suite: Mapped[TestSuite] = relationship(
        "TestSuite", back_populates="runs", foreign_keys=[suite_id]
    )
    children: Mapped[list[Run]] = relationship(
        "Run", foreign_keys=[parent_run_id], back_populates="parent"
    )
    parent: Mapped[Run | None] = relationship(
        "Run", foreign_keys=[parent_run_id], back_populates="children", remote_side=[id]
    )
    results: Mapped[list[TestResult]] = relationship(
        "TestResult", back_populates="run", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# TestResult
# ---------------------------------------------------------------------------

class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    test_case_id: Mapped[str] = mapped_column(
        String, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )

    # ── which model produced this result (new) ─────────────────────────────
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)

    # ── adapter output ─────────────────────────────────────────────────────
    final_response: Mapped[str] = mapped_column(Text, default="")
    actual_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full per-result trace:
    # [{'step', 'tool', 'params', 'response', 'tokens_this_step',
    #   'expected_tool', 'is_divergence', 'divergence_reason'}, ...]
    execution_trace: Mapped[list | None] = mapped_column(JSON, nullable=True)

    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── assertion results ──────────────────────────────────────────────────
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    divergence_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assertion_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── LLM-as-judge ──────────────────────────────────────────────────────
    semantic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    # relationships
    run: Mapped[Run] = relationship("Run", back_populates="results")
    test_case: Mapped[TestCase] = relationship("TestCase", back_populates="results")
