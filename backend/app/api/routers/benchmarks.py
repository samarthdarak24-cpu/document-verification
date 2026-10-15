"""Benchmark endpoints (``/api/benchmarks``)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import bad_request, get_db
from app.models import BenchmarkResult
from app.schemas import BenchmarkRequest, BenchmarkRowOut
from app.services.benchmarking import (
    algorithm_names,
    dataset_names,
    known_case_types,
    run_algorithm_benchmarks,
    summarise,
    persist_benchmark_rows,
    SIZES,
)

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("/options")
def benchmark_options():
    """The algorithms, datasets and sizes the benchmark suite can run."""
    return {
        "algorithms": algorithm_names(),
        "datasets": dataset_names(),
        "sizes": list(SIZES),
        "case_types": known_case_types(),
    }


@router.post("/run")
def run_benchmarks(payload: BenchmarkRequest, db: Session = Depends(get_db)):
    """Run real benchmarks with ``perf_counter_ns`` and ``tracemalloc``.

    Every row is measured on this machine, right now. Nothing is fabricated:
    an algorithm that cannot run on a dataset simply yields no row.
    """
    unknown = [a for a in (payload.algorithms or []) if a not in algorithm_names()]
    if unknown:
        raise bad_request(f"Unknown algorithm(s): {', '.join(unknown)}.")
    bad_sets = [d for d in (payload.datasets or []) if d not in dataset_names()]
    if bad_sets:
        raise bad_request(f"Unknown dataset(s): {', '.join(bad_sets)}.")
    if payload.sizes:
        if any(size < 1 or size > 100_000 for size in payload.sizes):
            raise bad_request("Sizes must be between 1 and 100,000.")
        if len(payload.sizes) > 10:
            raise bad_request("At most 10 sizes may be requested per run.")

    started = time.perf_counter()
    rows = run_algorithm_benchmarks(
        algorithms=payload.algorithms or None,
        datasets=payload.datasets or None,
        sizes=payload.sizes or None,
        repeats=payload.repeats,
    )
    stored = 0
    if payload.persist and rows:
        stored = persist_benchmark_rows(db, rows)
        db.flush()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    return {
        "rows": [BenchmarkRowOut.model_validate(row) for row in rows],
        "stored": stored,
        "summary": summarise(rows),
        "elapsed_ms": round(elapsed_ms, 2),
    }


@router.get("")
def list_benchmarks(
    db: Session = Depends(get_db),
    algorithm: str | None = None,
    dataset_type: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
):
    """Stored benchmark measurements, newest first."""
    stmt = select(BenchmarkResult).order_by(BenchmarkResult.created_at.desc())
    if algorithm:
        stmt = stmt.where(BenchmarkResult.algorithm == algorithm)
    if dataset_type:
        stmt = stmt.where(BenchmarkResult.dataset_type == dataset_type)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {"items": [BenchmarkRowOut.model_validate(row) for row in rows]}


@router.get("/summary")
def benchmark_summary(db: Session = Depends(get_db)):
    """Aggregate benchmark statistics per algorithm, computed in SQL."""
    rows = db.execute(
        select(
            BenchmarkResult.algorithm,
            func.count(BenchmarkResult.id),
            func.min(BenchmarkResult.execution_time_ms),
            func.avg(BenchmarkResult.execution_time_ms),
            func.max(BenchmarkResult.execution_time_ms),
        ).group_by(BenchmarkResult.algorithm)
    ).all()
    return {
        "algorithms": [
            {
                "algorithm": algorithm,
                "runs": count,
                "min_ms": round(float(minimum or 0), 4),
                "avg_ms": round(float(average or 0), 4),
                "max_ms": round(float(maximum or 0), 4),
            }
            for algorithm, count, minimum, average, maximum in rows
        ]
    }


@router.get("/export.csv")
def export_benchmarks_csv(
    db: Session = Depends(get_db),
    algorithm: str | None = None,
):
    """Download stored benchmark rows as CSV for offline analysis."""
    from fastapi.responses import PlainTextResponse

    stmt = select(BenchmarkResult).order_by(
        BenchmarkResult.algorithm, BenchmarkResult.input_size
    )
    if algorithm:
        stmt = stmt.where(BenchmarkResult.algorithm == algorithm)
    rows = db.execute(stmt).scalars().all()

    header = (
        "algorithm,input_size,dataset_type,case_type,execution_time_ms,"
        "memory_bytes,operations,repeats,created_at\n"
    )
    lines = [
        f"{row.algorithm},{row.input_size},{row.dataset_type},{row.case_type},"
        f"{row.execution_time_ms},{row.memory_bytes},{row.operations},{row.repeats},"
        f"{row.created_at.isoformat() if row.created_at else ''}"
        for row in rows
    ]
    csv_body = header + "\n".join(lines) + ("\n" if lines else "")
    return PlainTextResponse(
        csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=docutrace-benchmarks.csv"},
    )
