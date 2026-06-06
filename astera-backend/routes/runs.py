"""
routes/runs.py
Run management endpoints — POST to start, GET to poll/report/replay/compare
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import uuid
from datetime import datetime, timezone

from db.database import get_db
from db.models import Run, TestResult, TestSuite, TestCase
from services.test_runner import execute_run

router = APIRouter()

SUPPORTED_MODELS = ["gemini", "gpt-4", "claude"]


# ---------------------------------------------------------------------------
# POST /api/runs  — start a run (single or multi-model)
# ---------------------------------------------------------------------------

@router.post("/runs", status_code=202)
async def start_run(body: dict, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Accepts: { suite_id, models_to_test: [...], multi_model_test: bool }
    Creates one Run record per model and fires a background task for each.
    Returns: { run_ids: [...], status: 'started' }
    """
    suite_id = body.get("suite_id")
    multi = body.get("multi_model_test", False)
    models = body.get("models_to_test", ["gemini"])

    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    if not models:
        models = suite.models_to_test or ["gemini"]

    bad = [m for m in models if m not in SUPPORTED_MODELS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unsupported model(s): {bad}")

    run_ids = []
    for model in models:
        run = Run(
            id=str(uuid.uuid4()),
            suite_id=suite_id,
            model_type=model,
            multi_model_test=multi,
            models_to_test=models,
            status="pending",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        bg.add_task(_safe_execute_run, run.id)
        run_ids.append(run.id)

    return {"run_ids": run_ids, "status": "started", "models_queued": models}


# ---------------------------------------------------------------------------
# GET /api/runs  — recent run history (dashboard)
# ---------------------------------------------------------------------------

@router.get("/runs")
async def get_recent_runs(db: Session = Depends(get_db), limit: int = 10):
    """Fetch recent run history for the dashboard."""
    runs = (
        db.query(Run)
        .order_by(Run.started_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for run in runs:
        suite = db.query(TestSuite).filter(TestSuite.id == run.suite_id).first()
        result.append({
            "run_id": run.id,
            "suite_id": run.suite_id,
            "suite_name": suite.name if suite else "Unknown",
            "model_type": run.model_type,
            "status": run.status,
            "pass_count": run.pass_count,
            "fail_count": run.fail_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        })

    return result


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}/status  — live poll
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/status")
async def get_run_status(run_id: str, db: Session = Depends(get_db)):
    """Poll endpoint — returns current status and per-test-case progress."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    results = db.query(TestResult).filter(TestResult.run_id == run_id).all()

    trace_logs = [
        {
            "test_case_id": r.test_case_id,
            "passed": r.passed,
            "steps": len(r.execution_trace) if r.execution_trace else 0,
        }
        for r in results
    ]

    return {
        "run_id": run_id,
        "status": run.status,
        "model_type": run.model_type,
        "pass_count": run.pass_count,
        "fail_count": run.fail_count,
        "total_tokens": run.total_tokens,
        "trace_logs": trace_logs,
        "started_at": run.started_at.isoformat() if run.started_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}/report  — full completed report
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: str, db: Session = Depends(get_db)):
    """Fetch full completed report with all test results."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    results = db.query(TestResult).filter(TestResult.run_id == run_id).all()

    result_data = []
    for result in results:
        test_case = db.query(TestCase).filter(TestCase.id == result.test_case_id).first()
        result_data.append({
            "test_case_id": result.test_case_id,
            "prompt": test_case.prompt if test_case else "",
            "passed": result.passed,
            "execution_trace": result.execution_trace or [],
            "divergence_step": result.divergence_step,
            "semantic_score": result.semantic_score,
            "judge_explanation": result.judge_explanation,
            "token_usage": result.token_usage,
            "actual_response": result.actual_response,
            "expected_tools": test_case.expected_tools if test_case else [],
            "model_used": result.model_used,
        })

    return {
        "run_id": run_id,
        "suite_id": run.suite_id,
        "model_type": run.model_type,
        "status": run.status,
        "pass_count": run.pass_count,
        "fail_count": run.fail_count,
        "total_tokens": run.total_tokens,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "results": result_data,
    }


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}/replay  — Agent Replay Mode
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/replay")
async def get_run_replay(run_id: str, db: Session = Depends(get_db)):
    """Return the full execution trace for Agent Replay Mode visualisation."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    suite = db.query(TestSuite).filter(TestSuite.id == run.suite_id).first()
    results = db.query(TestResult).filter(TestResult.run_id == run_id).all()

    execution_traces = []
    semantic_scores = []
    for result in results:
        execution_traces.append({
            "test_case_id": result.test_case_id,
            "execution_trace": result.execution_trace or [],
            "divergence_step": result.divergence_step,
            "is_divergence": result.divergence_step is not None,
        })
        if result.semantic_score is not None:
            semantic_scores.append({
                "test_case_id": result.test_case_id,
                "score": result.semantic_score,
            })

    return {
        "run_id": run_id,
        "model_used": run.model_type,
        "suite_name": suite.name if suite else "",
        "execution_trace_replay": execution_traces,
        "pass_count": run.pass_count or 0,
        "fail_count": run.fail_count or 0,
        "total_tokens": run.total_tokens or 0,
        "semantic_scores": semantic_scores,
        "status": run.status,
    }


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}/compare  — multi-model side-by-side
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/compare")
async def compare_run_results(run_id: str, db: Session = Depends(get_db)):
    """Side-by-side comparison of all models tested for the same suite."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    all_runs = db.query(Run).filter(Run.suite_id == run.suite_id).all()

    comparison = {}
    for r in all_runs:
        results = db.query(TestResult).filter(TestResult.run_id == r.id).all()
        total_tests = len(results)
        passed = sum(1 for res in results if res.passed)

        semantic_scores = [res.semantic_score for res in results if res.semantic_score is not None]
        avg_semantic = round(sum(semantic_scores) / len(semantic_scores), 1) if semantic_scores else None

        comparison[r.model_type] = {
            "run_id": r.id,
            "pass_count": passed,
            "fail_count": total_tests - passed,
            "pass_rate": f"{(passed / total_tests * 100):.1f}%" if total_tests > 0 else "0%",
            "total_tokens": r.total_tokens,
            "avg_semantic_score": avg_semantic,
            "status": r.status,
        }

    return {"suite_id": run.suite_id, "models": comparison}


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------

async def _safe_execute_run(run_id: str) -> None:
    """Fire execute_run and mark the run failed if it crashes."""
    try:
        await execute_run(run_id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("execute_run failed for run_id=%s", run_id)
        try:
            from db.database import SessionLocal
            db = SessionLocal()
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = "failed"
                db.commit()
            db.close()
        except Exception:
            pass
