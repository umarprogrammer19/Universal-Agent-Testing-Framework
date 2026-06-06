"""
services/test_runner.py

Executes a single Run record that already exists in the DB.
routes/runs.py creates one Run per model and fires execute_run(run.id)
for each — this function works with that exact run, saves TestResult
records against it, and updates its status/counters when done.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from db.database import SessionLocal
from db.models import Run, TestSuite, TestCase, TestResult
from services.adapters.factory import AdapterFactory
from services.judge import judge_response

logger = logging.getLogger(__name__)

SUPPORTED_MODELS: list[str] = ["gemini", "gpt-4", "claude"]


# ---------------------------------------------------------------------------
# Public entry point — called as a FastAPI BackgroundTask
# ---------------------------------------------------------------------------

async def execute_run(run_id: str) -> None:
    """
    Drive one Run to completion.

    1. Load the Run (already created by the route) and its suite's test cases.
    2. Create the right adapter for run.model_type.
    3. Execute every test case, persist TestResult records.
    4. Update run.pass_count / fail_count / total_tokens / status.
    """
    db = SessionLocal()
    try:
        # ── Fetch run ──────────────────────────────────────────────────────
        run: Run | None = db.query(Run).filter(Run.id == run_id).first()
        if run is None:
            logger.error("execute_run: Run %s not found", run_id)
            return

        run.status = "running"
        db.commit()

        # ── Fetch test cases ───────────────────────────────────────────────
        test_cases: list[TestCase] = (
            db.query(TestCase)
            .filter(TestCase.suite_id == run.suite_id)
            .order_by(TestCase.order_index)
            .all()
        )
        if not test_cases:
            logger.warning("execute_run: Suite %s has no test cases", run.suite_id)
            run.status = "failed"
            db.commit()
            return

        # ── Create adapter ─────────────────────────────────────────────────
        adapter = await AdapterFactory.create(run.model_type)

        # ── Execute each test case ─────────────────────────────────────────
        pass_count = 0
        fail_count = 0
        total_tokens = 0

        for test_case in test_cases:
            result = await _execute_test_case(
                db=db,
                run=run,
                test_case=test_case,
                adapter=adapter,
                model_name=run.model_type,
            )
            total_tokens += result.token_usage or 0
            if result.passed:
                pass_count += 1
            else:
                fail_count += 1

        # ── Update run ─────────────────────────────────────────────────────
        run.pass_count = pass_count
        run.fail_count = fail_count
        run.total_tokens = total_tokens
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Run %s completed | model=%s pass=%d fail=%d tokens=%d",
            run_id, run.model_type, pass_count, fail_count, total_tokens,
        )

    except Exception:
        logger.exception("execute_run crashed for run_id=%s", run_id)
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Per-test-case execution
# ---------------------------------------------------------------------------

async def _execute_test_case(
    db: Any,
    run: Run,
    test_case: TestCase,
    adapter: Any,
    model_name: str,
) -> TestResult:
    """Run one test case, assert, judge, persist."""

    # ── Call adapter ───────────────────────────────────────────────────────
    try:
        adapter_output: dict = await adapter.run_with_trace(
            prompt=test_case.prompt,
            tools=test_case.tools or [],
        )
    except Exception as exc:
        logger.exception(
            "Adapter error on test_case=%s model=%s", test_case.id, model_name
        )
        return _persist_result(
            db=db,
            run=run,
            test_case=test_case,
            model_name=model_name,
            final_response="",
            execution_trace=[],
            token_usage=0,
            passed=False,
            assertion_details={"error": str(exc)},
            semantic_score=None,
            judge_explanation=f"Adapter error: {exc}",
        )

    final_response: str = adapter_output.get("final_response", "")
    execution_trace: list[dict] = adapter_output.get("execution_trace", [])
    token_usage: int = adapter_output.get("token_usage", 0)

    # ── Assertion engine ───────────────────────────────────────────────────
    passed, assertion_details = _run_assertions(
        execution_trace=execution_trace,
        expected_tools=test_case.expected_tools or [],
        expected_output=getattr(test_case, "expected_output", None),
        final_response=final_response,
    )

    # ── LLM judge (only when golden_response is set) ───────────────────────
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

    # ── Persist ────────────────────────────────────────────────────────────
    return _persist_result(
        db=db,
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

    details: dict[str, Any] = {
        "tool_sequence_match": True,
        "missing_tools": [],
        "extra_tools": [],
        "divergent_steps": [],
        "output_match": None,
    }

    actual_tools = [step.get("tool", "") for step in execution_trace]

    if actual_tools != expected_tools:
        details["tool_sequence_match"] = False
        details["missing_tools"] = [t for t in expected_tools if t not in actual_tools]
        details["extra_tools"] = [t for t in actual_tools if t not in expected_tools]

    details["divergent_steps"] = [
        {
            "step": step.get("step"),
            "expected": step.get("expected_tool"),
            "actual": step.get("tool"),
            "reason": step.get("divergence_reason"),
        }
        for step in execution_trace
        if step.get("is_divergence")
    ]

    if expected_output is not None:
        details["output_match"] = expected_output.strip() == final_response.strip()

    # If no expected_tools were set, treat as pass (informational run only)
    if not expected_tools:
        passed = True
    else:
        passed = (
            details["tool_sequence_match"]
            and not details["divergent_steps"]
            and (details["output_match"] is not False)
        )

    return passed, details


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

def _persist_result(
    db: Any,
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

    # First divergence step index (1-based, None if no divergence)
    divergence_step: int | None = None
    for step in execution_trace:
        if step.get("is_divergence"):
            divergence_step = step.get("step", 0) + 1
            break

    result = TestResult(
        run_id=run.id,
        test_case_id=test_case.id,
        model_used=model_name,
        final_response=final_response,
        actual_response=final_response,
        execution_trace=execution_trace,
        token_usage=token_usage,
        passed=passed,
        divergence_step=divergence_step,
        assertion_details=assertion_details,
        semantic_score=semantic_score,
        judge_explanation=judge_explanation,
        created_at=datetime.now(timezone.utc),
    )
    db.add(result)
    db.flush()
    return result
