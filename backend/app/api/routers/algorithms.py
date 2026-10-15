"""Algorithm Laboratory endpoints (``/api/algorithms``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.algorithm_registry import AlgorithmError, list_algorithms, run_algorithm
from app.api.deps import bad_request, get_db
from app.models import AlgorithmRun

router = APIRouter(prefix="/algorithms", tags=["algorithms"])


@router.get("")
def get_algorithms():
    """Metadata for every algorithm (unit, complexity, parameters)."""
    return {"algorithms": list_algorithms()}


@router.post("/run")
def run(payload: dict):
    """Execute one algorithm on the caller's input and return real measurements."""
    algorithm = str(payload.get("algorithm") or "").strip()
    inputs = payload.get("inputs") or {}
    if not algorithm:
        raise bad_request("'algorithm' is required.")
    if not isinstance(inputs, dict):
        raise bad_request("'inputs' must be an object.")
    try:
        return run_algorithm(algorithm, inputs)
    except AlgorithmError as exc:
        raise bad_request(str(exc)) from None


@router.get("/history")
def algorithm_history(
    db: Session = Depends(get_db),
    algorithm: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Recently recorded algorithm executions from real verification runs."""
    from sqlalchemy import select

    stmt = select(AlgorithmRun).order_by(AlgorithmRun.created_at.desc())
    if algorithm:
        stmt = stmt.where(AlgorithmRun.algorithm == algorithm)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "algorithm": row.algorithm,
                "document_id": row.document_id,
                "run_id": row.run_id,
                "execution_time_ms": row.execution_time_ms,
                "operation_count": row.operation_count,
                "input_summary": row.input_summary,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }
