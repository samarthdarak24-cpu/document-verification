"""Verification report endpoints (``/api/reports``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import bad_request, get_db, not_found
from app.models import GeneratedReport, ReportType, VerificationRun
from app.schemas import ReportExportRequest, ReportGenerateRequest, ReportOut
from app.services.reporting import (
    comparison_report_json,
    list_reports,
    render_comparison_report,
    render_verification_report,
    resolve_report_path,
    save_json_payload,
    verification_report_json,
)

router = APIRouter(prefix="/reports", tags=["reports"])

#: Content type for each artifact the report renderer can produce.
_ARTIFACT_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".json": "application/json",
}


def _report(db: Session, report_id: str) -> GeneratedReport:
    report = db.get(GeneratedReport, report_id)
    if report is None:
        raise not_found("Report", report_id)
    return report


@router.get("")
def get_reports(db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500)):
    """All generated reports, newest first."""
    return {"items": [ReportOut.model_validate(r) for r in list_reports(db, limit)]}


@router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    """Report metadata."""
    return ReportOut.model_validate(_report(db, report_id))


@router.get("/{report_id}/download")
def download_report(
    report_id: str,
    db: Session = Depends(get_db),
    inline: bool = Query(False),
):
    """Download the stored artifact (PDF or JSON).

    The format is derived from the stored file, not assumed: a report generated
    with `format: "json"` is saved as `json/{run_id}.json`, and labelling that
    file `application/pdf` hands the browser a file named `.pdf` that is
    actually JSON — which the PDF viewer then refuses to render.
    """
    report = _report(db, report_id)
    path = resolve_report_path(report.relative_path)
    if not path.exists():
        raise not_found("Report file", report_id)

    suffix = path.suffix.lower()
    medium_type = _ARTIFACT_MEDIA_TYPES.get(suffix, "application/octet-stream")
    return FileResponse(
        path,
        media_type=medium_type,
        filename=f"docutrace-{report.report_type}-{report.report_uuid[:8]}{suffix}",
        content_disposition_type="inline" if inline else "attachment",
    )


@router.get("/{report_id}/json")
def report_json(report_id: str, db: Session = Depends(get_db)):
    """Return the report as JSON, rebuilt from the stored verification run.

    The JSON is regenerated from persisted run data, so it always reflects what
    the algorithms actually measured rather than a cached summary.
    """
    report = _report(db, report_id)
    if report.report_type == ReportType.VERIFICATION:
        if not report.run_id:
            raise bad_request("This report is not linked to a verification run.")
        run = db.get(VerificationRun, report.run_id)
        if run is None:
            raise not_found("Verification run", report.run_id or "")
        return JSONResponse(verification_report_json(db, run))
    if not report.relative_path:
        raise bad_request("This report has no stored payload.")
    raise bad_request("Comparison reports are exported as PDF; re-run /api/compare for JSON.")


@router.post("/{run_id}/generate", status_code=201)
def generate_report(
    run_id: str,
    payload: ReportGenerateRequest,
    db: Session = Depends(get_db),
):
    """(Re)generate a report for a verification run, in PDF or JSON."""
    run = db.get(VerificationRun, run_id)
    if run is None:
        raise not_found("Verification run", run_id)

    if payload.format == "json":
        body = verification_report_json(db, run)
        relative = f"json/{run_id}.json"
        save_json_payload(body, relative)
        report = GeneratedReport(
            run_id=run.id,
            document_id=run.document_id,
            report_uuid=body["report_uuid"],
            report_type=ReportType.VERIFICATION,
            relative_path=relative,
        )
        db.add(report)
        db.flush()
        return {"report": ReportOut.model_validate(report), "payload": body}

    artifact = render_verification_report(db, run)
    report = GeneratedReport(
        run_id=run.id,
        document_id=run.document_id,
        report_uuid=artifact.report_uuid,
        report_type=ReportType.VERIFICATION,
        relative_path=artifact.relative_path,
    )
    db.add(report)
    db.flush()
    return {"report": ReportOut.model_validate(report), "artifact": artifact.to_dict()}


@router.post("/export/comparison")
def export_comparison_report(payload: ReportExportRequest):
    """Render a comparison PDF from a compare payload (stateless export)."""
    body = payload.payload.model_dump()
    json_payload = comparison_report_json(body)
    artifact = render_comparison_report(
        json_payload, comparison_id=payload.comparison_id
    )
    return FileResponse(
        artifact.absolute_path,
        media_type="application/pdf",
        filename=f"docutrace-comparison-{artifact.report_uuid[:8]}.pdf",
    )
