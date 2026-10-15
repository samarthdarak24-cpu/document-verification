"""Integration tests for the change-detection and PDF-metadata endpoints.

Exercises the real FastAPI app against the isolated test database, uploading
genuine PDFs so the whole path (upload -> store -> resolve -> analyse) is
covered rather than the services in isolation.
"""

from __future__ import annotations

import io

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
BASE_LINES = [
    "Registration Number: MH/2024/008421",
    "Holder Name: Ananya R. Deshmukh",
    "Date of Issue: 2024-04-12",
    "Status: Active",
]


def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _w, h = A4
    y = h - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, title)
    y -= 32
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def _upload(client, filename: str, lines: list[str]) -> str:
    response = client.post(
        "/api/documents/upload",
        files={"file": (filename, _pdf_bytes("Certificate", lines), "application/pdf")},
        data={"doc_type": "certificate"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["document"]["id"]


# --------------------------------------------------------------------------- #
# POST /api/changes/text
# --------------------------------------------------------------------------- #
class TestTextChangeEndpoint:
    def test_single_digit_change(self, client):
        response = client.post(
            "/api/changes/text",
            json={
                "original_text": "Registration Number: MH/2024/008421",
                "modified_text": "Registration Number: MH/2024/008422",
            },
        )
        assert response.status_code == 200, response.text
        report = response.json()["report"]
        assert report["changed"] is True
        assert report["verdict"] == "content_replaced"
        assert "lcs_dp" in report["algorithms_executed"]
        assert "edit_distance" in report["algorithms_executed"]

    def test_identical_text(self, client):
        response = client.post(
            "/api/changes/text",
            json={"original_text": "same text", "modified_text": "same text"},
        )
        assert response.status_code == 200
        assert response.json()["report"]["verdict"] == "identical"

    def test_oversized_text_is_rejected(self, client):
        huge = "x" * 2_000_001
        response = client.post(
            "/api/changes/text",
            json={"original_text": huge, "modified_text": "y"},
        )
        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# POST /api/changes/detect
# --------------------------------------------------------------------------- #
class TestDetectEndpoint:
    def test_detects_a_changed_field(self, client):
        source = _upload(client, "original.pdf", BASE_LINES)
        changed = [
            line.replace("008421", "008422") for line in BASE_LINES
        ]
        target = _upload(client, "modified.pdf", changed)

        response = client.post(
            "/api/changes/detect",
            json={"source_document_id": source, "target_document_id": target},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["report"]["changed"] is True
        assert body["report"]["style_change_count"] >= 0
        assert body["source_document"]["filename"] == "original.pdf"
        assert body["target_document"]["filename"] == "modified.pdf"

    def test_identical_documents_report_no_change(self, client):
        source = _upload(client, "one.pdf", BASE_LINES)
        target = _upload(client, "two.pdf", BASE_LINES)
        response = client.post(
            "/api/changes/detect",
            json={"source_document_id": source, "target_document_id": target},
        )
        assert response.status_code == 200
        assert response.json()["report"]["changed"] is False

    def test_same_document_is_rejected(self, client):
        source = _upload(client, "only.pdf", BASE_LINES)
        response = client.post(
            "/api/changes/detect",
            json={"source_document_id": source, "target_document_id": source},
        )
        assert response.status_code == 400

    def test_unknown_document_is_404(self, client):
        source = _upload(client, "known.pdf", BASE_LINES)
        response = client.post(
            "/api/changes/detect",
            json={"source_document_id": source, "target_document_id": "does-not-exist"},
        )
        assert response.status_code == 404


# --------------------------------------------------------------------------- #
# GET /api/documents/{id}/pdf-metadata
# --------------------------------------------------------------------------- #
class TestPdfMetadataEndpoint:
    def test_summary_is_returned(self, client):
        document_id = _upload(client, "meta.pdf", BASE_LINES)
        response = client.get(f"/api/documents/{document_id}/pdf-metadata")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["page_count"] == 1
        assert body["span_count"] > 0
        fonts = {item["value"] for item in body["style_summary"]["fonts"]}
        assert "Helvetica-Bold" in fonts
        assert body["truncated"] is False
        assert "blocks" not in body["pages"][0]

    def test_include_spans_returns_layout_detail(self, client):
        document_id = _upload(client, "meta2.pdf", BASE_LINES)
        response = client.get(
            f"/api/documents/{document_id}/pdf-metadata?include_spans=true"
        )
        assert response.status_code == 200
        body = response.json()
        spans = [
            span
            for page in body["pages"]
            for block in page.get("blocks", [])
            for span in block["spans"]
        ]
        assert spans
        assert all("font" in span and "bbox" in span for span in spans)

    def test_span_cap_is_enforced(self, client):
        document_id = _upload(client, "meta3.pdf", BASE_LINES)
        response = client.get(
            f"/api/documents/{document_id}/pdf-metadata?include_spans=true&max_spans=2"
        )
        assert response.status_code == 200
        body = response.json()
        emitted = sum(
            len(block["spans"])
            for page in body["pages"]
            for block in page.get("blocks", [])
        )
        assert emitted <= 2
        assert body["truncated"] is True

    def test_non_pdf_is_rejected(self, client):
        response = client.post(
            "/api/documents/upload",
            files={"file": ("notes.txt", b"just some text", "text/plain")},
            data={"doc_type": "unknown"},
        )
        assert response.status_code in (200, 201), response.text
        document_id = response.json()["document"]["id"]
        response = client.get(f"/api/documents/{document_id}/pdf-metadata")
        assert response.status_code == 400

    def test_unknown_document_is_404(self, client):
        response = client.get("/api/documents/nope/pdf-metadata")
        assert response.status_code == 404
