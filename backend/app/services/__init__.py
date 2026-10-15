"""DocuTrace service layer.

Each module is a pure-ish unit that takes explicit inputs (paths, text, ORM
rows) and returns dataclasses, so the pipeline can time and record each stage
independently:

==========================  =====================================================
Module                      Responsibility
==========================  =====================================================
``extraction``              PDF / DOCX / image / text -> text (+ optional OCR)
``pdf_metadata``            Span-level PDF layout (font/size/style/colour/position)
``document_change_detector``What changed between two documents (LCS + edit distance)
``normalization``           Unicode + date + currency + numeric normalization
``field_validation``        Template-driven field extraction and validation
``structure``               Heading-based document tree + structural validation
``similarity``              Candidate generation and bounded document comparison
``duplicate_detection``     Staged duplicate detection + duplicate group upkeep
``verification``            Deterministic rule engine (R001..R008)
``reporting``               ReportLab PDF + JSON report rendering
``benchmarking``            Real measured benchmarks over generated datasets
==========================  =====================================================

``ServiceError`` is the single exception type services raise for *expected*
failure modes (corrupt file, unsupported type, missing template). The pipeline
catches it and records the message on the document instead of crashing the
request.
"""

from __future__ import annotations


class ServiceError(Exception):
    """An expected, recoverable service failure.

    Raised for corrupt files, unsupported formats and bad inputs. The upload
    pipeline catches it and marks the document ``upload_status="failed"`` with
    the message stored in ``documents.error_message`` — a failed upload must
    never take down the worker.
    """

    def __init__(self, message: str, code: str = "service_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


__all__ = ["ServiceError"]
