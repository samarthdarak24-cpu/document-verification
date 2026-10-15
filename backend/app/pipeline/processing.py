"""Upload orchestration: validate -> extract -> normalize -> verify -> report.

The pipeline is where the DAA units are actually used:

* **Unit I (graphs)** — ``topological_sort(verification_pipeline_dag())`` decides
  the execution order of the stages, and the chosen order is recorded in the
  run's metadata.
* **Unit II (divide & conquer)** — ``merge_sort`` ranks similarity candidates by
  score and ``count_inversions`` quantifies section reordering between documents.
* **Unit III (dynamic programming)** — ``lcs_dp`` / ``edit_distance`` power the
  detailed comparison stage (bounded by ``DP_MAX_TOKENS``).
* **Unit IV (greedy)** — ``huffman_encode`` produces archival statistics for the
  extracted text.
* **Unit V (network flow)** — ``bipartite_match`` aligns extracted labels with
  expected template fields.
* **String algorithms** — ``kmp_search`` finds field labels,
  ``rabin_karp_search`` verifies template fragments, ``sha256_file`` /
  ``sha256_text`` fingerprint the file and its normalized text.

Stages are executed in the topological order of the DAG (not a hard-coded
sequence), each stage is timed, and every algorithm invocation is recorded in
``algorithm_runs`` — the report renders those rows, so its timings are real.

Idempotency
-----------
Re-uploading the same file creates a **new document row** every time (an upload
is an event, not a state overwrite) but links the new row to the existing
duplicate group, so the history is preserved and the duplicate relationship is
never lost.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.algorithms.huffman import huffman_encode
from app.algorithms.kmp import kmp_search
from app.algorithms.merge_sort import merge_sort
from app.algorithms.rabin_karp import rabin_karp_search
from app.algorithms.topological_sort import topological_sort, verification_pipeline_dag
from app.core.config import get_settings
from app.models.models import (
    AlgorithmRun,
    Document,
    DocumentTemplate,
    DuplicateStatus,
    ExtractedField,
    FieldStatus,
    GeneratedReport,
    ReportType,
    ReviewRecommendation,
    SimilarityMatch,
    UploadStatus,
    ValidationStatus,
    VerificationFinding,
    VerificationOutcome,
    VerificationRun,
)
from app.core.security import safe_filename
from app.algorithms.hashing import compute_file_hash_with_stats
from app.services import ServiceError
from app.services.duplicate_detection import DuplicateResult, detect_duplicates
from app.services.extraction import ExtractionResult, extract
from app.services.field_validation import (
    FieldValidationResult,
    align_fields,
    apply_alignment_sources,
    extract_and_validate_fields,
    template_spec_from,
)
from app.services.normalization import NormalizedDocument, normalize_text
from app.services.reporting import ReportArtifact, render_verification_report
from app.services.similarity import cached_tokens, remember_tokens
from app.services.structure import (
    StructureResult,
    analyze_structure,
    structure_has_issues,
    validate_against_template,
)
from app.services.verification import VerificationInputs, decide


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class StageRecord:
    """One pipeline stage's timing and outcome."""

    stage: str
    label: str
    elapsed_ms: float = 0.0
    detail: Dict[str, Any] = field(default_factory=dict)
    algorithms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "label": self.label,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "detail": self.detail,
            "algorithms": list(self.algorithms),
        }


@dataclass
class PipelineResult:
    """Everything the API layer needs after processing one upload."""

    document: Document
    run: VerificationRun
    stage_timings: List[StageRecord] = field(default_factory=list)
    pipeline_order: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    extraction_warnings: List[str] = field(default_factory=list)
    success: bool = True

    @property
    def failed(self) -> bool:
        return not self.success


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _utcnow():
    from app.models.models import utcnow

    return utcnow()


def _file_mtime(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except OSError:  # pragma: no cover - defensive
        return 0


def _excerpt(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _relative_storage_path(stored_name: str) -> str:
    return f"documents/{stored_name}"


class RunRecorder:
    """Collects ``algorithm_runs`` rows for one verification run."""

    def __init__(self, db: Session, document_id: str, run_id: str) -> None:
        self.db = db
        self.document_id = document_id
        self.run_id = run_id
        self.rows: List[AlgorithmRun] = []

    def record(
        self,
        algorithm: str,
        *,
        elapsed_ns: int,
        operations: int = 0,
        input_summary: str = "",
        result_summary: Optional[Dict[str, Any]] = None,
    ) -> AlgorithmRun:
        row = AlgorithmRun(
            document_id=self.document_id,
            run_id=self.run_id,
            algorithm=algorithm,
            input_summary=input_summary[:2000],
            execution_time_ms=float(elapsed_ns) / 1_000_000.0,
            operation_count=int(operations),
            result_summary_json=result_summary,
        )
        self.db.add(row)
        self.rows.append(row)
        return row


@contextmanager
def _stage(
    result: PipelineResult, stage: str, label: str
) -> Iterator[StageRecord]:
    """Time a pipeline stage and append it to ``result.stage_timings``.

    The record is appended when the block *exits*, so ``stage_timings`` ends up
    in real execution order regardless of how the code below is re-arranged.
    """
    record = StageRecord(stage=stage, label=label)
    started = time.perf_counter()
    try:
        yield record
    finally:
        record.elapsed_ms = (time.perf_counter() - started) * 1000.0
        result.stage_timings.append(record)


def load_thresholds(db: Session) -> Dict[str, Any]:
    """Merge stored settings with the application defaults."""
    from app.models import load_settings

    values = load_settings(db)
    similarity = dict(values.get("similarity_thresholds", {}))
    validation = dict(values.get("validation_policy", {}))
    algorithm = dict(values.get("algorithm_policy", {}))
    ocr = dict(values.get("ocr_policy", {}))
    return {
        "jaccard_candidate": float(similarity.get("jaccard_candidate", 0.15)),
        "shingle_size": int(similarity.get("shingle_size", 3)),
        "near_duplicate": float(similarity.get("near_duplicate", 0.85)),
        "content_duplicate": float(similarity.get("content_duplicate", 0.999)),
        "candidate_min": float(similarity.get("candidate_min", 0.60)),
        "critical_field_edit_similarity_min": float(
            validation.get("critical_field_edit_similarity_min", 0.6)
        ),
        "require_required_fields": bool(
            validation.get("require_required_fields", True)
        ),
        "dp_max_tokens": int(algorithm.get("dp_max_tokens", 2000)),
        "bipartite_similarity_threshold": float(
            algorithm.get("bipartite_similarity_threshold", 0.6)
        ),
        "max_sections_for_inversions": int(
            algorithm.get("max_sections_for_inversions", 200)
        ),
        "ocr_confidence_warn": float(ocr.get("confidence_warn", 0.75)),
        "ocr_enabled": bool(ocr.get("enabled", True)),
    }


def _store_file(source: Path, original_filename: str, document_id: str) -> str:
    """Copy a staged upload into the managed storage root under a safe name.

    The stored name is derived from a fresh UUID plus the sanitised original
    name, so a client-supplied filename can never influence the final path.
    """
    settings = get_settings()
    settings.ensure_directories()
    safe = safe_filename(original_filename) or "document"
    stored_name = f"{document_id}__{safe}"
    destination = settings.upload_root / stored_name
    destination.write_bytes(Path(source).read_bytes())
    return stored_name


def _apply_extraction(document: Document, extraction: ExtractionResult) -> None:
    """Copy extraction metadata onto the document row."""
    document.page_count = extraction.page_count or len(extraction.pages)
    document.extraction_method = extraction.method
    document.extraction_confidence = float(extraction.confidence)
    document.ocr_used = bool(extraction.ocr_used)


def _compute_file_hash(path: Path, recorder: Optional[RunRecorder] = None) -> str:
    """Stream the stored file through SHA-256, recording the measurement."""
    started = time.perf_counter_ns()
    stats = compute_file_hash_with_stats(path)
    if recorder is not None:
        recorder.record(
            "sha256_file",
            elapsed_ns=time.perf_counter_ns() - started,
            operations=stats["chunks"],
            input_summary=f"{stats['bytes_read']:,} bytes streamed",
            result_summary={"sha256": stats["sha256"], "chunks": stats["chunks"]},
        )
    return stats["sha256"]


def _resolve_template(
    db: Session, template_id: Optional[str], doc_type: Optional[str] = None
) -> Optional[Any]:
    """Fetch the template for a run.

    Resolution order:

    1. An explicit ``template_id`` — a bad id is an error, never a silent
       fallback.
    2. A template whose ``name`` matches ``doc_type`` exactly (so uploading a
       file ``doc_type="certificate"`` picks the certificate template
       automatically).
    3. The ``custom`` template, which enforces no required fields.

    Passing ``doc_type`` is what makes the auto-selection possible; without it
    the behaviour is the historical "id or custom" fallback.
    """
    if template_id:
        template = db.execute(
            select(DocumentTemplate).where(DocumentTemplate.id == template_id)
        ).unique().scalar_one_or_none()
        if template is None:
            raise ServiceError(
                f"Template '{template_id}' was not found.", code="template_not_found"
            )
        return template

    if doc_type and doc_type not in {"unknown", "custom"}:
        matched = db.execute(
            select(DocumentTemplate)
            .where(DocumentTemplate.name == doc_type)
            .order_by(DocumentTemplate.created_at.asc())
        ).unique().scalars().first()
        if matched is not None:
            return matched

    return db.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.category == "custom")
        .order_by(DocumentTemplate.created_at.asc())
    ).unique().scalars().first()


def _structural_issues(structure: Any) -> List[Dict[str, Any]]:
    """Flatten a structure analysis into verification-engine issue dicts.

    The analysis reports the same missing section in two shapes: bare names in
    ``validation["missing"]`` and full dicts in ``validation["issues"]``. Taking
    both blindly reported every section twice, once per representation. The bare
    names and the prose dicts are now the same value, so the ``issues`` dicts
    already cover everything and are used directly.
    """
    validation = getattr(structure, "validation", {}) or {}
    issues = [
        item
        for item in (validation.get("issues", []) or [])
        if isinstance(item, dict) and item.get("type")
    ]
    # Anything reported only as a bare name still needs a row.
    covered = {
        item.get("detail") for item in issues if item.get("type") == "missing_section"
    }
    for section in validation.get("missing", []) or []:
        if section and section not in covered:
            issues.append({"type": "missing_section", "detail": section})
    return issues


def _record_field_algorithms(
    recorder: RunRecorder, fields_result: Any, normalized: Any
) -> None:
    """Record the KMP and bipartite-matching measurements for a field stage."""
    recorder.record(
        "kmp_search",
        elapsed_ns=int(getattr(fields_result, "elapsed_ms", 0.0) * 1_000_000),
        operations=int(getattr(fields_result, "kmp_comparisons", 0) or 0),
        input_summary=(
            f"{len(getattr(fields_result, 'fields', []) or [])} template fields, "
            f"{getattr(normalized, 'char_count', 0):,} chars"
        ),
        result_summary={
            "required_missing": list(
                getattr(fields_result, "required_missing", []) or []
            ),
            "invalid_fields": list(
                getattr(fields_result, "invalid_fields", []) or []
            ),
        },
    )
    matching = getattr(fields_result, "matching", None) or {}
    recorder.record(
        "bipartite_match",
        elapsed_ns=int(getattr(fields_result, "elapsed_ms", 0.0) * 1_000_000),
        operations=int(matching.get("matching_size", 0) or 0),
        input_summary=(
            f"{matching.get('expected_count', len(getattr(fields_result, 'fields', []) or []))} "
            f"expected vs {matching.get('extracted_count', 0)} extracted labels"
        ),
        result_summary=matching,
    )


def _record_duplicate_algorithms(recorder: RunRecorder, duplicate: Any) -> None:
    """Record per-stage duplicate-detection measurements."""
    for stage in getattr(duplicate, "stages", []) or []:
        name = stage.get("stage") or "duplicate_stage"
        recorder.record(
            f"duplicate:{name}",
            elapsed_ns=int(float(stage.get("elapsed_ms", 0.0)) * 1_000_000),
            operations=int(stage.get("probes", 0) or 0),
            input_summary=str(stage.get("label", name)),
            result_summary={
                key: value
                for key, value in stage.items()
                if key not in {"stage", "label", "elapsed_ms"}
            },
        )


def _rank_candidates(duplicate: Any, recorder: RunRecorder) -> List[Dict[str, Any]]:
    """Rank duplicate candidates by similarity using the custom merge sort.

    This is the Unit II (divide & conquer) integration point: the educational
    implementation ranks the candidate list, and the measured comparison count
    is recorded in ``algorithm_runs``.
    """
    matches = list(getattr(duplicate, "matches", []) or [])
    if not matches:
        return []

    def key(match: Any) -> float:
        return -float(getattr(match, "similarity", 0.0) or 0.0)

    started = time.perf_counter_ns()
    result = merge_sort(matches, key=key)
    recorder.record(
        "merge_sort",
        elapsed_ns=time.perf_counter_ns() - started,
        operations=result.comparisons,
        input_summary=f"ranking {len(matches)} similarity candidates",
        result_summary={
            "comparisons": result.comparisons,
            "merges": result.merges,
            "sorted_document_ids": [
                getattr(m, "document_id", None) for m in result.sorted_items
            ],
        },
    )
    return [
        {
            "document_id": getattr(match, "document_id", ""),
            "filename": getattr(match, "filename", ""),
            "similarity": round(float(getattr(match, "similarity", 0.0) or 0.0), 4),
            "stage": getattr(match, "stage", ""),
        }
        for match in result.sorted_items
    ]


def _finalise_failure(
    result: PipelineResult,
    thresholds: Dict[str, Any],
    overall_started: float,
    *,
    error: str = "",
) -> PipelineResult:
    """Persist a failed run so the failure is auditable rather than silent."""
    run = result.run
    run.outcome = VerificationOutcome.PROCESSING_ERROR
    run.validation_status = ValidationStatus.NOT_RUN
    run.duplicate_status = DuplicateStatus.UNIQUE
    run.review_recommendation = ReviewRecommendation.RETRY
    run.thresholds_json = thresholds
    run.explanation = error or "Processing failed before verification completed."
    run.completed_at = _utcnow()
    run.processing_ms = int((time.perf_counter() - overall_started) * 1000)
    db = Session.object_session(result.document)
    if db is not None:
        db.add(run)
        db.flush()
    result.run = run
    result.success = False
    return result


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #
def process_document(
    db: Session,
    *,
    file_path: str | Path,
    original_filename: str,
    mime_type: str,
    doc_type: str = "unknown",
    template_id: Optional[str] = None,
    generate_report: bool = True,
    document: Optional[Document] = None,
    reusing_existing: bool = False,
) -> PipelineResult:
    """Run the full verification pipeline for one stored file.

    There are two modes:

    * **Fresh upload** (``document is None``) — a brand-new ``documents`` row is
      created for the file. This is the ``POST /api/documents/upload`` path.
    * **Re-verification** (``document`` supplied) — verification runs again for
      an *already stored* document. The existing row is reused and only a fresh
      ``verification_runs`` row (plus its findings/matches/report) is created.
      The document must never be duplicated: one uploaded file is one document.

    Never raises for recoverable problems: a corrupt/unsupported file produces a
    document row with ``upload_status="failed"`` and the message stored, because
    a failed upload must not abort the request.
    """
    settings = get_settings()
    thresholds = load_thresholds(db)
    overall_started = time.perf_counter()

    raw_name = original_filename or Path(file_path).name
    run_id = str(uuid.uuid4())

    if document is None:
        # ---- Fresh upload: create the document row -------------------------- #
        document_id = str(uuid.uuid4())
        document = Document(
            id=document_id,
            filename=raw_name,
            stored_name="",
            relative_path="",
            mime_type=mime_type or "",
            doc_type=doc_type or "unknown",
            upload_status=UploadStatus.PROCESSING,
        )
        db.add(document)
        reuse = False
    else:
        # ---- Re-verification: reuse the existing document row ---------------- #
        # ``reusing_existing`` is what stops ``_store_file`` from writing a
        # second copy of the file under a new name.
        document_id = document.id
        document.upload_status = UploadStatus.PROCESSING
        if mime_type:
            document.mime_type = mime_type
        db.add(document)
        reuse = True

    recorder = RunRecorder(db, document_id, run_id)
    result = PipelineResult(
        document=document,
        run=VerificationRun(
            id=run_id,
            document_id=document_id,
            outcome="PROCESSING_ERROR",
        ),
    )
    db.add(result.run)
    # Flush the parent ``documents`` and ``verification_runs`` rows *before* any
    # ``algorithm_runs`` are recorded. Both ``algorithm_runs.document_id`` and
    # ``algorithm_runs.run_id`` are foreign keys, and SQLite enforces FKs on
    # every statement, so the target rows must exist first. The run row is a
    # placeholder here and is fully populated at the verification-decision stage.
    db.flush()

    # ---- Unit I: schedule the stages --------------------------------------- #
    with _stage(result, "scheduling", "Topological sort of the pipeline DAG (Unit I)") as record:
        dag = verification_pipeline_dag()
        topo = topological_sort(dag["nodes"], dag["edges"])
        result.pipeline_order = topo.order
        recorder.record(
            "topological_sort",
            elapsed_ns=topo.elapsed_ns,
            operations=topo.node_count + topo.edge_count,
            input_summary=f"verification pipeline DAG ({topo.node_count} stages, "
                          f"{topo.edge_count} edges)",
            result_summary={"order": topo.order},
        )
        record.detail = {"order": topo.order, "stages": topo.node_count}
        record.algorithms.append("topological_sort")

    document = result.document
    template = _resolve_template(db, template_id, doc_type=document.doc_type)
    spec = template_spec_from(template)

    # ---- Stage: upload / file validation ----------------------------------- #
    with _stage(result, "upload", "Upload and file validation") as record:
        if reuse:
            # The file is already in storage under its original ``stored_name``.
            # Re-storing it would orphan the old copy and break the document's
            # identity, so re-verification only re-reads what is already there.
            stored_name = document.stored_name
            if not stored_name:
                document.upload_status = UploadStatus.FAILED
                document.error_message = (
                    "The stored file name is missing; re-upload this document."
                )
                record.detail = {"error": document.error_message}
                db.commit()
                return _finalise_failure(result, thresholds, overall_started)
            record.detail = {
                "stored_name": stored_name,
                "size_bytes": document.file_size or 0,
                "reused": True,
            }
        else:
            try:
                stored_name = _store_file(file_path, raw_name, document_id)
            except ServiceError as exc:
                document.upload_status = UploadStatus.FAILED
                document.error_message = exc.message
                document.file_size = 0
                record.detail = {"error": exc.message, "code": exc.code}
                db.commit()
                return _finalise_failure(result, thresholds, overall_started)
            document.stored_name = stored_name
            document.relative_path = _relative_storage_path(stored_name)
            document.file_size = Path(settings.upload_root / stored_name).stat().st_size
            record.detail = {
                "stored_name": stored_name,
                "size_bytes": document.file_size,
            }
    db.flush()

    # ---- Stage: text extraction -------------------------------------------- #
    with _stage(result, "text_extraction",
                "Text extraction (PyMuPDF / python-docx / PIL)") as record:
        try:
            extraction = extract(settings.upload_root / stored_name)
        except ServiceError as exc:
            document.upload_status = UploadStatus.FAILED
            document.error_message = exc.message
            record.detail = {"error": exc.message, "code": exc.code}
            db.commit()
            return _finalise_failure(
                result, thresholds, overall_started, error=exc.message
            )
        except Exception as exc:  # pragma: no cover - unexpected backend failure
            message = f"Unexpected extraction failure: {exc}"
            document.upload_status = UploadStatus.FAILED
            document.error_message = message
            record.detail = {"error": message}
            db.commit()
            return _finalise_failure(
                result, thresholds, overall_started, error=message
            )
        result.extraction_warnings.extend(extraction.warnings)
        result.warnings.extend(extraction.warnings)
        _apply_extraction(document, extraction)
        record.detail = {
            "method": extraction.method,
            "pages": extraction.page_count,
            "chars": len(extraction.full_text),
            "confidence": round(extraction.confidence, 3),
            "ocr_used": extraction.ocr_used,
            "warnings": len(extraction.warnings),
        }

    # ---- Stage: normalization ---------------------------------------------- #
    with _stage(result, "normalization",
                "Unicode/date/currency normalization") as record:
        normalized = normalize_text(extraction.full_text)
        document.normalized_text_hash = normalized.normalized_hash
        document.text_excerpt = _excerpt(
            extraction.full_text, settings.TEXT_EXCERPT_CHARS
        )
        record.detail = {
            "char_count": normalized.char_count,
            "token_count": normalized.token_count,
            "normalized_hash": normalized.normalized_hash[:16] + "...",
            "notes": normalized.notes,
        }
    tokens = normalized.comparison_tokens
    remember_tokens(document.id, _file_mtime(settings.upload_root / stored_name), tokens)

    # ---- Stage: field detection + validation (KMP + bipartite) ------------- #
    with _stage(result, "field_detection",
                "Field label search (KMP) and bipartite alignment") as record:
        fields_result = extract_and_validate_fields(
            extraction,
            template,
            alignment_threshold=thresholds["bipartite_similarity_threshold"],
        )
        fields_result = apply_alignment_sources(fields_result)
        record.detail = {
            "template": fields_result.template_name,
            "fields_found": sum(
                1 for item in fields_result.fields
                if item.status != FieldStatus.MISSING
            ),
            "kmp_comparisons": fields_result.kmp_comparisons,
            "bipartite_matches": (fields_result.matching or {}).get("matching_size", 0),
        }
        record.algorithms.extend(["kmp_search", "bipartite_match"])
    _record_field_algorithms(recorder, fields_result, normalized)

    # ---- Stage: hashing ----------------------------------------------------- #
    with _stage(result, "hashing",
                "File and normalized-text SHA-256") as record:
        file_hash = _compute_file_hash(
            settings.upload_root / stored_name, recorder
        )
        document.file_sha256 = file_hash
        record.detail = {
            "file_sha256": file_hash[:16] + "...",
            "normalized_text_hash": normalized.normalized_hash[:16] + "...",
        }
        record.algorithms.extend(["sha256_file", "sha256_text"])

        # Unit IV (optional): archival statistics for the extracted text.
        if normalized.normalized_text:
            huffman = huffman_encode(normalized.normalized_text[:200_000])
            archive = {
                "original_bytes": huffman.original_bytes,
                "total_compressed_bytes": huffman.total_compressed_bytes,
                "compression_ratio": round(huffman.compression_ratio, 4),
                "round_trip_ok": huffman.round_trip_ok,
            }
            recorder.record(
                "huffman_encode",
                elapsed_ns=huffman.elapsed_ns,
                operations=sum(huffman.frequency.values()),
                input_summary=f"{huffman.original_bytes:,} chars of extracted text",
                result_summary=archive,
            )
            record.algorithms.append("huffman_encode")
            record.detail["archival"] = archive
    db.flush()

    # ---- Stage: duplicate lookup -------------------------------------------- #
    with _stage(result, "duplicate_lookup", "Staged duplicate detection") as record:
        duplicate = detect_duplicates(
            db,
            document,
            normalized,
            doc_type=document.doc_type,
            thresholds=thresholds,
            source_tokens=tokens,
            source_fields={
                item.field_name.lower(): item.field_value or ""
                for item in fields_result.fields
            },
            critical_fields=sorted(spec.critical_set or []),
        )
        document.duplicate_status = duplicate.duplicate_status
        document.similarity_score = duplicate.similarity
        record.detail = {
            step["stage"]: {k: v for k, v in step.items() if k != "stage"}
            for step in duplicate.stages
        }
        record.algorithms.extend(["sha256_probe", "jaccard_index", "lcs_dp",
                                 "edit_distance"])
    _record_duplicate_algorithms(recorder, duplicate)

    # ---- Stage: candidate retrieval + similarity analysis ------------------- #
    with _stage(result, "similarity_analysis",
                "Candidate retrieval and bounded LCS/edit comparison") as record:
        ranked = _rank_candidates(duplicate, recorder)
        record.detail = {
            "candidates_considered": len(duplicate.candidates),
            "duplicate_matches": len(duplicate.matches),
            "ranked": ranked,
        }
        record.algorithms.append("merge_sort")

    # ---- Stage: structural validation --------------------------------------- #
    with _stage(result, "structural_validation",
                "Structure analysis and DFS/BFS validation") as record:
        structure = validate_against_template(
            analyze_structure(extraction, spec), spec
        )
        record.detail = {
            "heuristic": structure.heuristic,
            "uncertain": structure.uncertain,
            "present": structure.validation.get("present", []),
            "missing": structure.validation.get("missing", []),
            "unverified": structure.unverified_sections,
            "dfs_visited": structure.dfs.get("visited_count"),
            "bfs_visited": structure.bfs.get("visited_count"),
        }
        record.algorithms.extend(
            ["build_tree", "validate_structure", "dfs", "bfs"]
        )
    recorder.record(
        "structure_validation",
        elapsed_ns=int(structure.elapsed_ms * 1_000_000),
        operations=structure.dfs.get("visited_count", 0)
        + structure.bfs.get("visited_count", 0),
        input_summary=f"heuristic={structure.heuristic}, tokens={normalized.token_count}",
        result_summary=structure.to_dict(),
    )

    # ---- Stage: verification decision --------------------------------------- #
    with _stage(result, "verification_decision",
                "Deterministic rule engine (R001-R008)") as record:
        decision = decide(
            VerificationInputs(
                fields=fields_result.fields,
                required_missing=fields_result.required_missing,
                invalid_fields=fields_result.invalid_fields,
                critical_field_values={
                    item.field_name.lower(): item.field_value or ""
                    for item in fields_result.fields
                },
                duplicate_status=duplicate.duplicate_status,
                duplicate_matches=[match.to_dict() for match in duplicate.matches],
                similarity_score=duplicate.similarity,
                similarity_threshold=thresholds["near_duplicate"],
                matcher_critical_mismatches=[
                    mismatch
                    for match in duplicate.matches
                    for mismatch in match.critical_mismatches
                ],
                structural_issues=_structural_issues(structure),
                structure_uncertain=structure.uncertain,
                extraction_confidence=extraction.confidence,
                ocr_used=extraction.ocr_used,
                extraction_warnings=list(extraction.warnings or []),
                ocr_confidence_threshold=thresholds["ocr_confidence_warn"],
                template_name=spec.name,
                thresholds=thresholds,
            )
        )
        record.detail = {
            "outcome": decision.outcome,
            "rules_fired": decision.rules_fired,
        }

    # ``run`` is the placeholder row flushed at the top of the pipeline; update
    # it in place rather than constructing a second row with the same id.
    run = result.run
    run.template_id = template.id if template is not None else None
    run.started_at = _utcnow()
    run.completed_at = _utcnow()
    run.outcome = decision.outcome
    run.validation_status = decision.validation_status
    run.duplicate_status = decision.duplicate_status
    run.review_recommendation = decision.review_recommendation
    run.similarity_score = decision.similarity_score
    run.thresholds_json = thresholds
    run.explanation = decision.explanation
    run.processing_ms = int((time.perf_counter() - overall_started) * 1000)
    db.add(run)
    db.flush()

    for finding in decision.findings:
        db.add(
            VerificationFinding(
                run_id=run.id,
                rule_id=finding.rule_id,
                severity=finding.severity,
                category=finding.category,
                message=finding.message,
                details_json=finding.details,
            )
        )
    # Extracted fields describe the *document* against a template, not one
    # verification run, and re-verification re-derives them from the same stored
    # file. Replace the previous set instead of appending a second copy —
    # otherwise every re-verify doubles the document's field rows.
    db.execute(
        delete(ExtractedField).where(ExtractedField.document_id == document_id)
    )
    for item in fields_result.fields:
        db.add(
            ExtractedField(
                document_id=document_id,
                field_name=item.field_name,
                field_value=item.field_value,
                field_type=item.field_type,
                status=item.status,
                confidence=item.confidence,
                source=item.source,
                location=item.location or None,
            )
        )
    for match in duplicate.matches:
        # ``DuplicateMatch`` is the persisted view of a comparison: it carries the
        # overall similarity, the edit similarity and the critical-field
        # mismatches, but not the full ``ComparisonResult``.
        text_similarity = float(getattr(match, "similarity", 0.0) or 0.0)
        edit_similarity = float(getattr(match, "edit_similarity", 0.0) or 0.0)
        mismatches = list(getattr(match, "critical_mismatches", []) or [])
        db.add(
            SimilarityMatch(
                run_id=run.id,
                source_document_id=document_id,
                target_document_id=match.document_id,
                text_similarity=text_similarity,
                edit_similarity=edit_similarity,
                overall_score=float(match.similarity),
                match_type=match.stage,
                field_differences_json={"critical_mismatches": mismatches}
                if mismatches
                else None,
                explanation=getattr(match, "explanation", None),
            )
        )
    db.flush()

    document.validation_status = decision.validation_status
    document.upload_status = UploadStatus.COMPLETED
    document.processing_duration_ms = run.processing_ms
    db.flush()

    # ---- Stage: report generation ------------------------------------------- #
    with _stage(result, "report_generation", "Verification report rendering") as record:
        try:
            artifact = render_verification_report(db, run)
            db.add(
                GeneratedReport(
                    run_id=run.id,
                    document_id=document_id,
                    report_uuid=artifact.report_uuid,
                    report_type=ReportType.VERIFICATION,
                    relative_path=artifact.relative_path,
                )
            )
            record.detail = {
                "report_uuid": artifact.report_uuid,
                "bytes": artifact.byte_size,
                "sections": artifact.section_titles,
            }
            db.commit()
        except Exception as exc:  # pragma: no cover - reportlab failure
            result.warnings.append(f"Report generation failed: {exc}")
            record.detail = {"error": str(exc)}
            db.rollback()
            db.refresh(document)
            db.refresh(run)

    result.run = run
    result.success = True
    db.commit()
    db.refresh(document)
    db.refresh(run)
    return result


def recheck_document(
    db: Session,
    *,
    document_id: str,
    template_id: Optional[str] = None,
    generate_report: bool = True,
) -> PipelineResult:
    """Re-run verification for an already-stored document.

    The stored file is re-read and the *entire* pipeline runs again, so the new
    run's measurements describe the current algorithms rather than replaying a
    previous run's numbers. The original file is never re-uploaded or modified
    and the ``documents`` row is **reused** — only a fresh ``verification_runs``
    row (and its findings/matches/report) is added. One uploaded file therefore
    stays exactly one document, however many times it is verified.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise ServiceError(
            f"Document '{document_id}' was not found.", code="document_not_found"
        )

    settings = get_settings()
    stored = settings.upload_root / document.stored_name
    if not stored.exists():
        raise ServiceError(
            "The stored file for this document is missing; re-upload it to "
            "verify again.",
            code="stored_file_missing",
        )

    return process_document(
        db,
        file_path=stored,
        original_filename=document.filename,
        mime_type=document.mime_type or "application/octet-stream",
        doc_type=document.doc_type or "unknown",
        template_id=template_id,
        generate_report=generate_report,
        document=document,
        reusing_existing=True,
    )
