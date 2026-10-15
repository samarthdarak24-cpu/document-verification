"""Staged duplicate detection with duplicate-group maintenance.

Stages (each one cheaper than the next, and each one short-circuiting)
----------------------------------------------------------------------
1. **File hash** — O(1) index probe on ``documents.file_sha256`` (SHA-256 of the
   raw bytes). A hit means the two uploads are byte-identical.
2. **Normalized text hash** — O(1) index probe on
   ``documents.normalized_text_hash`` (SHA-256 of the *normalized* text). A hit
   means "same content, different file" (e.g. re-exported PDF, different cover
   page image, different metadata).
3. **Candidate retrieval** — same ``doc_type`` plus a token-set Jaccard filter
   over 3-gram shingles (see :mod:`app.services.similarity`). This is where the
   O(n^2) blow-up is avoided.
4. **Detailed bounded comparison** — LCS + edit similarity on the capped token
   lists of the surviving candidates only.
5. **Critical field + structural checks** — a high text similarity is *not*
   sufficient: two invoices from the same template with different invoice
   numbers are near-duplicates, but a changed critical field makes the second
   document internally inconsistent rather than a mere copy. The rule engine in
   :mod:`app.services.verification` consumes this result.

Two hard rules
--------------
* **Never group by filename.** Filenames are user-controlled metadata; two
  files called ``invoice.pdf`` are not duplicates, and a duplicate is often
  named differently on purpose. Only content fingerprints create groups.
* **Never claim legal forgery.** A duplicate is a duplicate; what it *means* is
  up to a human reviewer. The duplicate status is a factual classification.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import (
    Document,
    DuplicateGroup,
    GroupType,
    HashType,
)
from app.services import ServiceError
from app.services.normalization import NormalizedDocument
from app.services.similarity import (
    Candidate,
    ComparisonResult,
    compare_documents,
    find_candidates,
)

# Stage labels used in the returned ``stages`` list.
STAGE_FILE_HASH = "file_hash"
STAGE_TEXT_HASH = "text_hash"
STAGE_CANDIDATES = "candidate_retrieval"
STAGE_DETAILED = "detailed_comparison"
STAGE_FIELDS = "critical_field_checks"


@dataclass
class DuplicateMatch:
    """A document that this document duplicates (or nearly does)."""

    document_id: str
    filename: str
    stage: str
    similarity: float
    edit_similarity: float = 0.0
    critical_mismatches: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "stage": self.stage,
            "similarity": round(self.similarity, 4),
            "edit_similarity": round(self.edit_similarity, 4),
            "critical_mismatches": list(self.critical_mismatches),
        }


@dataclass
class DuplicateResult:
    """The outcome of every duplicate stage for one document."""

    duplicate_status: str = "unique"
    stage: str = "none"
    matches: List[DuplicateMatch] = field(default_factory=list)
    candidates: List[Candidate] = field(default_factory=list)
    stages: List[Dict[str, Any]] = field(default_factory=list)
    group_id: Optional[str] = None
    similarity: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_status in {
            "exact_duplicate", "content_duplicate", "near_duplicate",
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duplicate_status": self.duplicate_status,
            "stage": self.stage,
            "matches": [match.to_dict() for match in self.matches],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "stages": list(self.stages),
            "group_id": self.group_id,
            "similarity": self.similarity,
            "notes": list(self.notes),
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


def detect_duplicates(
    db: Session,
    document: Document,
    normalized: NormalizedDocument,
    *,
    doc_type: str,
    thresholds: Dict[str, Any],
    source_tokens: Optional[Sequence[str]] = None,
    source_fields: Optional[Dict[str, str]] = None,
    critical_fields: Optional[Sequence[str]] = None,
    max_candidates: int = 25,
) -> DuplicateResult:
    """Run every duplicate stage for ``document`` and maintain duplicate groups."""
    started = time.perf_counter()
    result = DuplicateResult()
    tokens = list(source_tokens) if source_tokens is not None else list(
        normalized.comparison_tokens
    )
    jaccard_threshold = float(thresholds.get("jaccard_candidate", 0.15))
    near_threshold = float(thresholds.get("near_duplicate", 0.85))
    content_threshold = float(thresholds.get("content_duplicate", 0.999))
    shingle_size = int(thresholds.get("shingle_size", 3))

    # ---- Stage 1: byte-identical file -------------------------------------- #
    stage_started = time.perf_counter()
    exact = _find_by_hash(db, document.file_sha256, exclude_id=document.id)
    stage_ms = (time.perf_counter() - stage_started) * 1000
    result.stages.append(
        {
            "stage": STAGE_FILE_HASH,
            "label": "File SHA-256 index probe",
            "probe": document.file_sha256[:16] + "...",
            "matches": len(exact),
            "elapsed_ms": round(stage_ms, 3),
        }
    )
    if exact:
        match = exact[0]
        result.duplicate_status = "exact_duplicate"
        result.stage = STAGE_FILE_HASH
        result.similarity = 1.0
        result.matches.append(
            DuplicateMatch(
                document_id=match.id,
                filename=match.filename,
                stage=STAGE_FILE_HASH,
                similarity=1.0,
            )
        )
        result.notes.append(
            "Byte-identical to a previously uploaded file (SHA-256 index probe)."
        )
        result.group_id = _upsert_group(
            db, HashType.FILE, document.file_sha256, GroupType.EXACT,
            [document.id, match.id],
        )
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    # ---- Stage 2: identical normalized text -------------------------------- #
    stage_started = time.perf_counter()
    content = _find_by_text_hash(db, normalized.normalized_hash, exclude_id=document.id)
    stage_ms = (time.perf_counter() - stage_started) * 1000
    result.stages.append(
        {
            "stage": STAGE_TEXT_HASH,
            "label": "Normalized-text SHA-256 index probe",
            "probe": normalized.normalized_hash[:16] + "...",
            "matches": len(content),
            "elapsed_ms": round(stage_ms, 3),
        }
    )
    if content:
        match = content[0]
        result.duplicate_status = "content_duplicate"
        result.stage = STAGE_TEXT_HASH
        result.similarity = 1.0
        result.matches.append(
            DuplicateMatch(
                document_id=match.id,
                filename=match.filename,
                stage=STAGE_TEXT_HASH,
                similarity=1.0,
            )
        )
        result.notes.append(
            "Identical after text normalization (different file bytes, same "
            "content) — normalized-text index probe."
        )
        result.group_id = _upsert_group(
            db, HashType.NORMALIZED_TEXT, normalized.normalized_hash,
            GroupType.CONTENT, [document.id, match.id],
        )
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    # ---- Stage 3: candidate retrieval -------------------------------------- #
    stage_started = time.perf_counter()
    others = _other_documents(db, document.id, doc_type)
    candidates = find_candidates(
        tokens,
        doc_type,
        [
            {
                "id": other.id,
                "filename": other.filename,
                "doc_type": other.doc_type,
                "comparison_tokens": list(other_tokens),
            }
            for other, other_tokens in others
        ],
        jaccard_threshold=jaccard_threshold,
        shingle_size=shingle_size,
    )
    stage_ms = (time.perf_counter() - stage_started) * 1000
    result.candidates = candidates[:max_candidates]
    result.stages.append(
        {
            "stage": STAGE_CANDIDATES,
            "label": "Same doc_type + 3-gram Jaccard candidate retrieval",
            "scanned": len(others),
            "candidates": len(candidates),
            "threshold": jaccard_threshold,
            "elapsed_ms": round(stage_ms, 3),
        }
    )
    if not candidates:
        result.notes.append(
            f"No candidate in the same document type reached the Jaccard "
            f"threshold of {jaccard_threshold}."
        )

    # ---- Stage 4: detailed bounded comparison ------------------------------- #
    token_map = {other.id: other_tokens for other, other_tokens in others}
    field_map = {other.id: other.fields for other, other_tokens in others}
    best: Optional[Tuple[Candidate, ComparisonResult]] = None
    stage_started = time.perf_counter()
    comparisons_run = 0
    for candidate in candidates[:max_candidates]:
        other_tokens = token_map.get(candidate.document_id, [])
        comparison = compare_documents(
            tokens,
            other_tokens,
            max_tokens=int(thresholds.get("dp_max_tokens", 2000)),
            source_fields=source_fields,
            target_fields={
                item.field_name.lower(): item.field_value or ""
                for item in field_map.get(candidate.document_id, [])
            },
            critical_fields=critical_fields,
            field_edit_similarity_min=float(
                thresholds.get("critical_field_edit_similarity_min", 0.6)
            ),
        )
        comparisons_run += 1
        if best is None or comparison.overall_score > best[1].overall_score:
            best = (candidate, comparison)
        if best[1].overall_score >= content_threshold:
            break  # cannot get better than "identical after comparison"
    stage_ms = (time.perf_counter() - stage_started) * 1000
    result.stages.append(
        {
            "stage": STAGE_DETAILED,
            "label": "Bounded LCS + edit-distance comparison",
            "comparisons": comparisons_run,
            "candidates_considered": min(len(candidates), max_candidates),
            "elapsed_ms": round(stage_ms, 3),
        }
    )

    if best is not None:
        candidate, comparison = best
        result.similarity = comparison.overall_score
        if comparison.overall_score >= content_threshold:
            result.duplicate_status = "content_duplicate"
            result.stage = STAGE_DETAILED
            result.notes.append(
                "Same content after comparison: the two documents are textually "
                f"identical ({comparison.overall_score:.4f})."
            )
        elif comparison.overall_score >= near_threshold:
            result.duplicate_status = "near_duplicate"
            result.stage = STAGE_DETAILED
            result.notes.append(
                f"Very similar to an existing document ({comparison.overall_score:.4f} "
                f">= {near_threshold})."
            )
        else:
            result.notes.append(
                f"Most similar existing document scores "
                f"{comparison.overall_score:.4f}, below the near-duplicate "
                f"threshold of {near_threshold}."
            )
        result.matches.append(
            DuplicateMatch(
                document_id=candidate.document_id,
                filename=candidate.filename,
                stage=STAGE_DETAILED,
                similarity=comparison.overall_score,
                edit_similarity=comparison.edit_similarity,
                critical_mismatches=[
                    entry for entry in comparison.field_differences
                    if entry.get("critical") and not entry.get("equal")
                ],
            )
        )

    if result.is_duplicate and result.matches:
        matched_ids = [document.id] + [match.document_id for match in result.matches]
        result.group_id = _upsert_group(
            db,
            HashType.FILE if result.duplicate_status == "exact_duplicate" else HashType.NORMALIZED_TEXT,
            normalized.normalized_hash,
            GroupType.EXACT if result.duplicate_status == "exact_duplicate" else GroupType.CONTENT,
            matched_ids,
        )

    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def _find_by_hash(db: Session, file_hash: str, exclude_id: str) -> List[Document]:
    if not file_hash:
        return []
    stmt = (
        select(Document)
        .where(Document.file_sha256 == file_hash, Document.id != exclude_id)
        .order_by(Document.uploaded_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _find_by_text_hash(db: Session, text_hash: str, exclude_id: str) -> List[Document]:
    if not text_hash:
        return []
    stmt = (
        select(Document)
        .where(
            Document.normalized_text_hash == text_hash,
            Document.id != exclude_id,
        )
        .order_by(Document.uploaded_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _other_documents(
    db: Session, exclude_id: str, doc_type: str
) -> List[Tuple[Document, List[str]]]:
    """Load candidate documents (same type) with their comparison tokens."""
    from app.services.normalization import normalize_for_comparison
    from app.services.similarity import cached_tokens, remember_tokens

    stmt = (
        select(Document)
        .where(
            Document.id != exclude_id,
            Document.upload_status == "completed",
            Document.doc_type == doc_type,
        )
        .order_by(Document.uploaded_at.desc())
        .limit(200)
    )
    documents = list(db.execute(stmt).scalars().all())
    pairs: List[Tuple[Document, List[str]]] = []
    for document in documents:
        tokens = cached_tokens(document.id, 0)
        if tokens is None:
            tokens = normalize_for_comparison(document.text_excerpt or "")
        pairs.append((document, tokens))
    return pairs


def _upsert_group(
    db: Session,
    hash_type: str,
    hash_value: str,
    group_type: str,
    document_ids: Sequence[str],
) -> str:
    """Create/extend a duplicate group and return its id."""
    existing = db.execute(
        select(DuplicateGroup).where(
            DuplicateGroup.hash_type == hash_type,
            DuplicateGroup.hash_value == hash_value,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = DuplicateGroup(
            hash_type=hash_type,
            hash_value=hash_value,
            group_type=group_type,
            document_ids_json=[],
        )
        db.add(existing)
    merged = list(existing.document_ids_json or [])
    for document_id in document_ids:
        if document_id and document_id not in merged:
            merged.append(document_id)
    existing.document_ids_json = merged
    existing.group_type = group_type
    db.flush()
    return existing.id


def list_duplicate_groups(db: Session, limit: int = 100) -> List[DuplicateGroup]:
    """Return the most recently created duplicate groups."""
    stmt = (
        select(DuplicateGroup)
        .order_by(DuplicateGroup.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def documents_in_group(db: Session, group: DuplicateGroup) -> List[Document]:
    """Resolve a group's document ids to rows (missing rows are skipped)."""
    ids = list(group.document_ids_json or [])
    if not ids:
        return []
    stmt = select(Document).where(Document.id.in_(ids))
    by_id = {document.id: document for document in db.execute(stmt).scalars().all()}
    return [by_id[document_id] for document_id in ids if document_id in by_id]


def require_document(db: Session, document_id: str) -> Document:
    """Return the document or raise :class:`ServiceError`."""
    document = db.get(Document, document_id)
    if document is None:
        raise ServiceError(f"Document {document_id!r} not found.", "document_not_found")
    return document
