"""
routes/suites.py
Test suite management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from db.database import get_db
from db.models import TestSuite, TestCase, Run, TestResult

router = APIRouter()


@router.get("/suites")
async def get_all_suites(db: Session = Depends(get_db)):
    """Fetch all test suites with metadata"""
    suites = db.query(TestSuite).all()

    result = []
    for suite in suites:
        test_count = db.query(TestCase).filter(TestCase.suite_id == suite.id).count()

        last_run = (
            db.query(Run)
            .filter(Run.suite_id == suite.id)
            .order_by(Run.started_at.desc())
            .first()
        )

        last_run_status = "never_run"
        if last_run:
            pass_c = last_run.pass_count or 0
            fail_c = last_run.fail_count or 0
            total = pass_c + fail_c
            last_run_status = f"{pass_c}/{total} passed"

        result.append({
            "id": suite.id,
            "name": suite.name,
            "multi_model_test": suite.multi_model_test,
            "models_to_test": suite.models_to_test or ["gemini"],
            "test_case_count": test_count,
            "last_run_status": last_run_status,
            "created_at": suite.created_at.isoformat() if suite.created_at else None,
        })

    return result


@router.post("/suites")
async def create_suite(body: dict, db: Session = Depends(get_db)):
    """Create a new test suite with test cases"""
    suite_id = str(uuid.uuid4())

    suite = TestSuite(
        id=suite_id,
        name=body.get("name"),
        multi_model_test=body.get("multi_model_test", False),
        models_to_test=body.get("models_to_test", ["gemini"]),
    )
    db.add(suite)
    db.flush()

    test_cases = body.get("test_cases", [])
    for idx, test_case in enumerate(test_cases):
        tc = TestCase(
            id=str(uuid.uuid4()),
            suite_id=suite_id,
            prompt=test_case.get("prompt"),
            expected_tools=test_case.get("expected_tools"),
            max_steps=test_case.get("max_steps", 5),
            golden_response=test_case.get("golden_response"),
            order_index=idx,
        )
        db.add(tc)

    db.commit()
    db.refresh(suite)

    return {
        "id": suite.id,
        "name": suite.name,
        "multi_model_test": suite.multi_model_test,
        "models_to_test": suite.models_to_test,
        "test_case_count": len(test_cases),
        "last_run_status": "never_run",
        "created_at": suite.created_at.isoformat() if suite.created_at else None,
    }


@router.get("/suites/{suite_id}")
async def get_suite(suite_id: str, db: Session = Depends(get_db)):
    """Fetch one suite with all its test cases"""
    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()

    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    test_cases = (
        db.query(TestCase)
        .filter(TestCase.suite_id == suite_id)
        .order_by(TestCase.order_index)
        .all()
    )

    cases_data = [
        {
            "id": tc.id,
            "prompt": tc.prompt,
            "expected_tools": tc.expected_tools,
            "max_steps": tc.max_steps,
            "golden_response": tc.golden_response,
            "order_index": tc.order_index,
        }
        for tc in test_cases
    ]

    return {
        "id": suite.id,
        "name": suite.name,
        "multi_model_test": suite.multi_model_test,
        "models_to_test": suite.models_to_test,
        "test_case_count": len(test_cases),
        "test_cases": cases_data,
        "created_at": suite.created_at.isoformat() if suite.created_at else None,
    }


@router.delete("/suites/{suite_id}")
async def delete_suite(suite_id: str, db: Session = Depends(get_db)):
    """Delete a suite and cascade delete all related data"""
    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()

    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    runs = db.query(Run).filter(Run.suite_id == suite_id).all()
    for run in runs:
        db.query(TestResult).filter(TestResult.run_id == run.id).delete()

    db.query(Run).filter(Run.suite_id == suite_id).delete()
    db.query(TestCase).filter(TestCase.suite_id == suite_id).delete()
    db.delete(suite)
    db.commit()

    return {"status": "deleted", "suite_id": suite_id}
