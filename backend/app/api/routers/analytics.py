"""Analytics endpoints (``/api/analytics``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import (
    AlgorithmRun,
    BenchmarkResult,
    Document,
    DuplicateGroup,
    GeneratedReport,
    VerificationFinding,
    VerificationRun,
)
from app.schemas import (
    AlgorithmUsageOut,
    AnalyticsDetailOut,
    AnalyticsOverviewOut,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _grouped(db: Session, column, model) -> dict:
    rows = db.execute(
        select(column, func.count(model.id)).group_by(column)
    ).all()
    return {str(key): int(count) for key, count in rows if key is not None}


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Aggregate dashboard metrics, all computed in SQL from real rows."""
    total = db.execute(select(func.count(Document.id))).scalar_one() or 0
    avg_similarity = db.execute(
        select(func.avg(Document.similarity_score)).where(
            Document.similarity_score.isnot(None)
        )
    ).scalar_one()
    avg_processing = db.execute(
        select(func.avg(Document.processing_duration_ms)).where(
            Document.processing_duration_ms.isnot(None)
        )
    ).scalar_one()
    avg_confidence = db.execute(
        select(func.avg(Document.extraction_confidence)).where(
            Document.extraction_confidence.isnot(None)
        )
    ).scalar_one()

    ocr_rows = db.execute(
        select(Document.ocr_used, func.count(Document.id)).group_by(Document.ocr_used)
    ).all()

    return AnalyticsOverviewOut(
        documents_total=total,
        documents_by_status=_grouped(db, Document.upload_status, Document),
        documents_by_type=_grouped(db, Document.doc_type, Document),
        documents_by_duplicate_status=_grouped(
            db, Document.duplicate_status, Document
        ),
        runs_by_outcome=_grouped(db, VerificationRun.outcome, VerificationRun),
        findings_by_rule=_grouped(db, VerificationFinding.rule_id, VerificationFinding),
        findings_by_severity=_grouped(
            db, VerificationFinding.severity, VerificationFinding
        ),
        ocr_usage={
            ("used" if bool(used) else "not_used"): int(count) for used, count in ocr_rows
        },
        extraction_methods=_grouped(
            db, Document.extraction_method, Document
        ),
        average_similarity=round(float(avg_similarity), 4) if avg_similarity else None,
        average_processing_ms=(
            round(float(avg_processing), 2) if avg_processing else None
        ),
        average_confidence=(
            round(float(avg_confidence), 4) if avg_confidence else None
        ),
        duplicate_groups=db.execute(
            select(func.count(DuplicateGroup.id))
        ).scalar_one() or 0,
        reports_generated=db.execute(
            select(func.count(GeneratedReport.id))
        ).scalar_one() or 0,
    )


@router.get("/algorithms")
def algorithm_analytics(db: Session = Depends(get_db)):
    """Algorithm usage and benchmark aggregates for the performance dashboard."""
    usage_rows = db.execute(
        select(
            AlgorithmRun.algorithm,
            func.count(AlgorithmRun.id),
            func.sum(AlgorithmRun.execution_time_ms),
            func.max(AlgorithmRun.execution_time_ms),
            func.avg(AlgorithmRun.operation_count),
        ).group_by(AlgorithmRun.algorithm)
    ).all()

    benchmark_rows = db.execute(
        select(
            BenchmarkResult.algorithm,
            func.count(BenchmarkResult.id),
            func.avg(BenchmarkResult.execution_time_ms),
            func.max(BenchmarkResult.execution_time_ms),
            func.avg(BenchmarkResult.memory_bytes),
        ).group_by(BenchmarkResult.algorithm)
    ).all()

    return AnalyticsDetailOut(
        algorithms=[
            AlgorithmUsageOut(
                algorithm=algorithm,
                executions=int(executions),
                total_ms=round(float(total or 0), 4),
                max_ms=round(float(maximum or 0), 4),
                avg_operations=round(float(avg_ops or 0), 2),
            )
            for algorithm, executions, total, maximum, avg_ops in usage_rows
        ],
        benchmarks={
            algorithm: {
                "runs": int(count),
                "avg_ms": round(float(avg or 0), 4),
                "max_ms": round(float(maximum or 0), 4),
                "avg_memory_bytes": round(float(avg_mem or 0), 1),
            }
            for algorithm, count, avg, maximum, avg_mem in benchmark_rows
        },
    )
