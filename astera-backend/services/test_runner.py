"""
services/test_runner.py

Orchestrates test-suite execution across one or multiple LLM adapters.
Each model gets its own Run record so the frontend can render a
side-by-side comparison without any ambiguity about which results
belong to which model.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports — these modules will be created separately
from database import get_db_session                          # async session factory
from models import Run, TestSuite, TestCase, TestResult     # ORM models
from services.adapters.factory import AdapterFactory
from services.judge import judge_response                    # LLM-as-judge scorer

logger = logging.getLogger(__name__)

# Models the framework knows how to test
SUPPORTED_MODELS: list[str] = ["gemini", "gpt-4", "claude"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def execute_run(run_id: str) -> dict[str, Any]:
    """
    Execute a test run (single-model or multi-model).

    Parameters
    ----------
    run_id : str
        Primary key of the Run record that was created when the user
        triggered this execution.

    Returns
    -------
    {
        'run_ids': [str, ...],          # one per model tested
        'model_results': {
            '<model>': {
                'run_id': str,
                'pass_count': int,
                'fail_count': int,
                'total_tokens': int,
            },
            ...
        }
    }
    """
    async with get_db_session() as session:
        # ── 1. Fetch the triggering Run from DB ──────────────────────────
        run: Run = await _fetch_run(session, run_id)
        suite: TestSuite = await _fetch_suite(session, run.suite_id)
        test_cases: list[TestCase] = await _fetch_test_cases(session, suite.id)

        # ── 2. Decide which models to test ───────────────────────────────
        if run.multi_model_test and run.models_to_test:
            models_to_run: list[str] = run.models_to_test
        else:
            models_to_run = [run.model_type]

        # ── 3. Execute each model (concurrently to reduce wall-clock time) ─
        tasks = [
            _run_single_model(
                session=session,
                parent_run=run,
                suite=suite,
                test_cases=test_cases,
                model_name=model_name,
            )
            for model_name in models_to_run
        ]
        model_summaries: list[dict[str, Any]] = await asyncio.gather(*tasks)

        # ── 4. Mark the parent run as completed ──────────────────────────
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        await session.commit()

    # ── 5. Build response for the API layer ──────────────────────────────
    run_ids = [s["run_id"] for s in model_summaries]
    model_results = {s["model"]: s for s in model_summaries}

    return {"run_ids": run_ids, "model_results": model_results}


# ---------------------------------------------------------------------------
# Per-model execution
# ---------------------------------------------------------------------------

async def _run_single_model(
    session: AsyncSession,
    parent_run: Run,
    suite: TestSuite,
    test_cases: list[TestCase],
    model_name: str,
) -> dict[str, Any]:
    """
    Create a child Run record, execute every test case against *model_name*,
    persist results, and return a summary dict.
    """
    # ── a. Create adapter ─────────────────────────────────────────────────
    adapter = await AdapterFactory.create(model_name)
    display_name = await adapter.get_model_name()
    logger.info("Starting run for model=%s (%s)", model_name, display_name)

    # ── b. Create a child Run record in DB ────────────────────────────────
    child_run = Run(
        suite_id=suite.id,
        model_type=model_name,
        model_display_name=display_name,
        parent_run_id=parent_run.id,
        status="running",
        started_at=datetime.now(timezone.utc),
        multi_model_test=False,   # child runs are always single-model
    )
    session.add(child_run)
    await session.flush()         # get child_run.id without committing

    # ── c. Execute each test case ─────────────────────────────────────────
    pass_count = 0
    fail_count = 0
    total_tokens = 0

    for test_case in test_cases:
        result = await _execute_test_case(
            session=session,
            run=child_run,
            test_case=test_case,
            adapter=adapter,
            model_name=model_name,
        )
        total_tokens += result.token_usage or 0
        if result.passed:
            pass_count += 1
        else:
            fail_count += 1

    # ── e. Update child Run record ────────────────────────────────────────
    child_run.pass_count = pass_count
    child_run.fail_count = fail_count
    child_run.total_tokens = total_tokens
    child_run.status = "completed"
    child_run.completed_at = datetime.now(timezone.utc)
    await session.commit()

    logger.info(
        "Completed run for model=%s | pass=%d fail=%d tokens=%d",
        model_name, pass_count, fail_count, total_tokens,
    )

    return {
        "model": model_name,
        "run_id": str(child_run.id),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total_tokens": total_tokens,
    }


# ---------------------------------------------------------------------------
# Per-test-case execution
# ---------------------------------------------------------------------------

async def _execute_test_case(
    session: AsyncSession,
    run: Run,
    test_case: TestCase,
    adapter: Any,
    model_name: str,
) -> TestResult:
    """
    Run one test case, compare the trace, optionally judge the response,
    and persist a TestResult record.
    """
    # ── d-i. Call adapter ─────────────────────────────────────────────────
    try:
        adapter_output: dict = await adapter.run_with_trace(
            prompt=test_case.prompt,
            tools=test_case.tools or [],
        )
    except Exception as exc:                                # adapter error
        logger.exception("Adapter error on test_case=%s model=%s", test_case.id, model_name)
        return await _persist_result(
            session=session,
            run=run,
            test_case=test_case,
            model_name=model_name,
            final_response="",
            execution_trace=[],
            token_usage=0,
            passed=False,
            assertion_details={"error": str(exc)},
            semantic_score=None,
            judge_explanation=f"Adapter raised an exception: {exc}",
        )

    final_response: str = adapter_output["final_response"]
    execution_trace: list[dict] = adapter_output["execution_trace"]
    token_usage: int = adapter_output["token_usage"]

    # ── d-ii. Assertion engine — compare actual vs expected tool sequence ─
    passed, assertion_details = _run_assertions(
        execution_trace=execution_trace,
        expected_tools=test_case.expected_tools or [],
        expected_output=test_case.expected_output,
        final_response=final_response,
    )

    # ── d-iii. LLM-as-judge (only when a golden response is provided) ─────
    semantic_score: float | None = None
    judge_explanation: str | None = None

    if test_case.golden_response:
        try:
            judge_result = await judge_response(
                prompt=test_case.prompt,
                golden=test_case.golden_response,
                actual=final_response,
            )
            semantic_score = judge_result.get("semantic_score")
            judge_explanation = judge_result.get("explanation")
        except Exception as exc:
            logger.warning("Judge failed for test_case=%s: %s", test_case.id, exc)
            judge_explanation = f"Judge error: {exc}"

    # ── d-iv. Persist TestResult ──────────────────────────────────────────
    return await _persist_result(
        session=session,
        run=run,
        test_case=test_case,
        model_name=model_name,
        final_response=final_response,
        execution_trace=execution_trace,
        token_usage=token_usage,
        passed=passed,
        assertion_details=assertion_details,
        semantic_score=semantic_score,
        judge_explanation=judge_explanation,
    )


# ---------------------------------------------------------------------------
# Assertion engine
# ---------------------------------------------------------------------------

def _run_assertions(
    execution_trace: list[dict],
    expected_tools: list[str],
    expected_output: str | None,
    final_response: str,
) -> tuple[bool, dict]:
    """
    Compare the actual tool-call sequence against expectations.

    Returns (passed: bool, details: dict) — details is stored in the DB
    so engineers can diagnose failures without re-running.
    """
    details: dict[str, Any] = {
        "tool_sequence_match": True,
        "missing_tools": [],
        "extra_tools": [],
        "divergent_steps": [],
        "output_match": None,
    }

    # ── Tool sequence check ───────────────────────────────────────────────
    actual_tools = [step["tool"] for step in execution_trace]

    if actual_tools != expected_tools:
        details["tool_sequence_match"] = False
        details["missing_tools"] = [t for t in expected_tools if t not in actual_tools]
        details["extra_tools"] = [t for t in actual_tools if t not in expected_tools]

    # Collect individual divergent steps already flagged by the adapter
    details["divergent_steps"] = [
        {
            "step": step["step"],
            "expected": step["expected_tool"],
            "actual": step["tool"],
            "reason": step["divergence_reason"],
        }
        for step in execution_trace
        if step.get("is_divergence")
    ]

    # ── Exact output check (optional) ────────────────────────────────────
    if expected_output is not None:
        details["output_match"] = expected_output.strip() == final_response.strip()

    # ── Overall pass/fail ─────────────────────────────────────────────────
    passed = (
        details["tool_sequence_match"]
        and not details["divergent_steps"]
        and (details["output_match"] is not False)   # None means "not checked" → ok
    )

    return passed, details


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------

async def _persist_result(
    session: AsyncSession,
    run: Run,
    test_case: TestCase,
    model_name: str,
    final_response: str,
    execution_trace: list[dict],
    token_usage: int,
    passed: bool,
    assertion_details: dict,
    semantic_score: float | None,
    judge_explanation: str | None,
) -> TestResult:
    result = TestResult(
        run_id=run.id,
        test_case_id=test_case.id,
        model_used=model_name,
        final_response=final_response,
        execution_trace=execution_trace,    # stored as JSON column
        token_usage=token_usage,
        passed=passed,
        assertion_details=assertion_details,
        semantic_score=semantic_score,
        judge_explanation=judge_explanation,
        created_at=datetime.now(timezone.utc),
    )
    session.add(result)
    await session.flush()
    return result


async def _fetch_run(session: AsyncSession, run_id: str) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run '{run_id}' not found in database.")
    return run


async def _fetch_suite(session: AsyncSession, suite_id: str) -> TestSuite:
    suite = await session.get(TestSuite, suite_id)
    if suite is None:
        raise ValueError(f"TestSuite '{suite_id}' not found in database.")
    return suite


async def _fetch_test_cases(session: AsyncSession, suite_id: str) -> list[TestCase]:
    from sqlalchemy import select
    stmt = select(TestCase).where(TestCase.suite_id == suite_id).order_by(TestCase.id)
    result = await session.execute(stmt)
    cases = result.scalars().all()
    if not cases:
        raise ValueError(f"TestSuite '{suite_id}' has no test cases.")
    return list(cases)
