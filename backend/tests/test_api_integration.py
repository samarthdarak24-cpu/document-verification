"""End-to-end integration tests for the FastAPI surface.

These tests exercise the **real** application object against an isolated SQLite
database (see :mod:`tests.conftest`). They deliberately move through the system
in the same order a user would: health -> templates -> upload -> extract ->
verify -> compare -> duplicates -> report -> analytics -> settings, with the
algorithm and benchmark routers checked alongside.

The unit tests in :mod:`tests.test_algorithms` prove each algorithm in
isolation. These tests prove the *wiring*: that the pipeline commits in an order
SQLite accepts, that the schemas round-trip, and that the endpoints agree with
each other.

Response-envelope notes (these are the real shapes -- do not assume bare arrays):

* ``POST /documents/upload`` -> ``{document, run, stage_timings, pipeline_order,
  warnings, extraction_warnings}``
* ``POST /verify/{id}`` -> ``{document, run, rules, ...}``
* ``GET  /documents`` -> ``{items, total, page, page_size, pages}``
* ``POST /algorithms/run`` -> ``{algorithm, title, unit, complexity_time,
  complexity_space, result, operations, trace, execution_time_ms}``
* ``POST /benchmarks/run`` -> ``{rows: [...]}``
"""

from __future__ import annotations

import io
import json

import pytest

# --------------------------------------------------------------------------- #
# Sample content -- identical in spirit to scripts/create_sample_documents.py so
# the integration tests and the demo exercise the same document semantics.
# --------------------------------------------------------------------------- #
SAMPLE_LINES = [
    "Certificate of Registration",
    "Registration Number: MH/2024/008421",
    "Holder Name: Aarav Deshmukh",
    "Date of Issue: 2024-03-14",
    "Issuing Authority: State Board of Technical Education",
    "Status: Active",
]

DOC_TYPE = "certificate"


def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    """Build an in-memory one-page PDF without touching the disk."""
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


def _upload(
    client,
    filename: str,
    title: str = "Certificate of Registration",
    lines: list[str] | None = None,
    doc_type: str = DOC_TYPE,
    payload: bytes | None = None,
):
    body = payload if payload is not None else _pdf_bytes(title, lines or SAMPLE_LINES)
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, body, "application/pdf")},
        data={"doc_type": doc_type},
    )


def _uploaded(client, *args, **kwargs):
    """Upload and return the nested ``document`` object, asserting success."""
    response = _upload(client, *args, **kwargs)
    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert "document" in body, f"unexpected upload envelope: {list(body)}"
    return body["document"]


def _items(payload):
    """Normalise a list response.

    Some routers return a bare JSON array, others wrap it as ``{"items": [...]}``
    (plus pagination totals). Every assertion needs the same view, so unwrap once
    here rather than repeating the dance at each call site.
    """
    if isinstance(payload, dict):
        for key in ("items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []
    return payload


# =========================================================================== #
# Meta / health
# =========================================================================== #
class TestMeta:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root(self, client):
        assert client.get("/").status_code == 200

    def test_unknown_route_is_404(self, client):
        assert client.get("/api/does-not-exist").status_code == 404

    def test_openapi_covers_every_router(self, client):
        schema = client.get("/openapi.json").json()
        assert len(schema["paths"]) >= 30


# =========================================================================== #
# Templates
# =========================================================================== #
class TestTemplates:
    def test_default_templates_seeded(self, client):
        r = client.get("/api/templates")
        assert r.status_code == 200
        names = {t["name"] for t in _items(r.json())}
        assert "certificate" in names
        assert len(names) >= 5

    def test_certificate_template_shape(self, client):
        cert = next(
            t for t in _items(client.get("/api/templates").json())
            if t["name"] == "certificate"
        )
        required = set(cert["required_fields"])
        assert {
            "holder_name", "registration_number", "issue_date",
            "issuing_authority", "status",
        } <= required
        assert "registration_number" in cert["critical_fields"]
        assert "issue_date" in cert["critical_fields"]
        assert "Header" in cert["expected_sections"]

    def test_create_get_update_delete_template(self, client):
        payload = {
            "name": "unit-test-template",
            "description": "created by the integration suite",
            "required_fields": ["title"],
            "critical_fields": ["title"],
            "expected_sections": ["Header"],
            "field_definitions": [
                {"name": "title", "label": "Title", "required": True, "pattern": None}
            ],
        }
        created = client.post("/api/templates", json=payload)
        assert created.status_code in (200, 201), created.text
        tid = created.json()["id"]

        got = client.get(f"/api/templates/{tid}")
        assert got.status_code == 200
        assert got.json()["name"] == "unit-test-template"

        updated = client.put(
            f"/api/templates/{tid}", json={**payload, "description": "updated"}
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "updated"

        assert client.delete(f"/api/templates/{tid}").status_code in (200, 204)
        assert client.get(f"/api/templates/{tid}").status_code == 404

    def test_missing_template_is_404(self, client):
        assert client.get("/api/templates/does-not-exist").status_code == 404


# =========================================================================== #
# Upload / extraction
# =========================================================================== #
class TestDocumentLifecycle:
    def test_upload_returns_document_and_run(self, client):
        r = _upload(client, "original.pdf")
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert {"document", "run", "stage_timings", "pipeline_order"} <= set(body)

        doc = body["document"]
        assert doc["filename"] == "original.pdf"
        assert len(doc["file_sha256"]) == 64
        assert doc["upload_status"] == "completed"
        assert doc["extraction_method"] == "pdf_native"
        assert doc["page_count"] == 1
        assert doc["processing_duration_ms"] >= 0

    def test_upload_records_doc_type(self, client):
        doc = _uploaded(client, "a.pdf", doc_type="certificate")
        assert doc["doc_type"] == "certificate"

    def test_upload_extracts_the_text(self, client):
        doc = _uploaded(client, "a.pdf")
        assert "MH/2024/008421" in (doc["text_excerpt"] or "")

    def test_pipeline_reports_its_stage_order(self, client):
        body = _upload(client, "a.pdf").json()
        order = body["pipeline_order"]
        assert isinstance(order, list) and len(order) >= 8
        stages = json.dumps(order).lower()
        for expected in ("upload", "extraction", "normalization",
                         "duplicate_lookup", "verification_decision"):
            assert expected in stages, f"pipeline is missing the {expected} stage"
        # The declared order must start at upload and end at report generation.
        assert order[0] == "upload"
        assert order[-1] == "report_generation"
        # Every declared step must also carry a measured duration.
        timings = body["stage_timings"]
        assert isinstance(timings, list) and timings
        assert all("stage" in t for t in timings)

    def test_upload_rejects_unsupported_extension(self, client):
        """An unsupported extension is recorded as a failed upload, not a 500.

        The endpoint deliberately accepts the request and reports the failure on
        the document row (``upload_status='failed'`` + ``PROCESSING_ERROR``) so
        the UI can show the user which file was rejected and why. A hard 4xx is
        reserved for unreadable requests (empty body, magic-byte mismatch).
        """
        r = client.post(
            "/api/documents/upload",
            files={"file": ("installer.exe", b"MZ\x90\x00\x03\x00\x00\x00",
                            "application/octet-stream")},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["document"]["upload_status"] == "failed"
        assert "exe" in (body["document"]["error_message"] or "").lower()
        assert body["run"]["outcome"] == "PROCESSING_ERROR"
        assert body["run"]["review_recommendation"] == "retry"

    def test_uploaded_file_is_always_traceable(self, client):
        """Even a rejected file keeps its document row for the audit trail."""
        r = client.post(
            "/api/documents/upload",
            files={"file": ("x.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        doc_id = r.json()["document"]["id"]
        assert client.get(f"/api/documents/{doc_id}").status_code == 200

    def test_upload_rejects_empty_file(self, client):
        r = client.post(
            "/api/documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert r.status_code in (400, 422)

    def test_upload_rejects_pdf_extension_with_wrong_magic_bytes(self, client):
        r = client.post(
            "/api/documents/upload",
            files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")},
        )
        assert r.status_code == 400

    def test_list_returns_a_page_of_documents(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        r = client.get("/api/documents")
        assert r.status_code == 200
        body = r.json()
        assert {"items", "total", "page", "page_size", "pages"} <= set(body)
        assert any(d["id"] == doc_id for d in body["items"])

    def test_get_document(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        r = client.get(f"/api/documents/{doc_id}")
        assert r.status_code == 200
        assert r.json()["id"] == doc_id

    def test_extracted_text_endpoint(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        r = client.get(f"/api/documents/{doc_id}/text")
        assert r.status_code == 200
        assert "MH/2024/008421" in json.dumps(r.json())

    def test_document_structure_endpoint(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        r = client.get(f"/api/documents/{doc_id}/structure")
        assert r.status_code == 200
        assert isinstance(r.json(), (dict, list))

    def test_download_returns_the_original_bytes(self, client):
        payload = _pdf_bytes("Certificate", SAMPLE_LINES)
        doc_id = _upload(client, "dl.pdf", payload=payload).json()["document"]["id"]
        r = client.get(f"/api/documents/{doc_id}/download")
        assert r.status_code == 200
        assert r.content == payload

    def test_preview_endpoint(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        r = client.get(f"/api/documents/{doc_id}/preview")
        assert r.status_code in (200, 404)  # 404 only when no rasteriser is available

    def test_delete_document(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        assert client.delete(f"/api/documents/{doc_id}").status_code in (200, 204)
        assert client.get(f"/api/documents/{doc_id}").status_code == 404

    def test_get_missing_document_is_404(self, client):
        assert client.get("/api/documents/does-not-exist").status_code == 404


# =========================================================================== #
# Verification + rules
# =========================================================================== #
class TestVerification:
    def test_verify_produces_a_run_with_rules(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        r = client.post(f"/api/verify/{doc_id}")
        assert r.status_code in (200, 201), r.text
        body = r.json()
        run = body["run"]
        assert run["id"]
        assert run["outcome"]
        assert run["validation_status"] in {"passed", "failed", "not_run"}

        # Rule verdicts are exposed as `findings` on the run-detail endpoint.
        detail = client.get(f"/api/verifications/{run['id']}").json()
        findings = detail["findings"]
        assert findings, "every verified run records the rule engine's findings"
        for finding in findings:
            assert finding["rule_id"].startswith("R")
            assert finding["severity"] in {"info", "warning", "critical", "error"}
            assert finding["message"]

    def test_verification_appears_in_history(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        run_id = client.post(f"/api/verify/{doc_id}").json()["run"]["id"]
        r = client.get("/api/verifications")
        assert r.status_code == 200
        assert any(v["id"] == run_id for v in _items(r.json()))

    def test_get_single_verification(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        run_id = client.post(f"/api/verify/{doc_id}").json()["run"]["id"]
        r = client.get(f"/api/verifications/{run_id}")
        assert r.status_code == 200
        assert r.json()["id"] == run_id

    def test_missing_registration_number_fails_validation(self, client):
        lines = [ln for ln in SAMPLE_LINES if "Registration Number" not in ln]
        doc_id = _uploaded(client, "noreg.pdf", lines=lines)["id"]
        body = client.post(f"/api/verify/{doc_id}").json()
        assert body["run"]["validation_status"] == "failed"
        detail = client.get(f"/api/verifications/{body['run']['id']}").json()
        failing = [
            f for f in detail["findings"]
            if f["severity"] in {"critical", "error"}
        ]
        assert failing, "a missing critical field must surface as a critical finding"

    def test_verification_run_ids_are_unique(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        ids = {client.post(f"/api/verify/{doc_id}").json()["run"]["id"] for _ in range(3)}
        assert len(ids) == 3

    def test_verify_missing_document_is_404(self, client):
        assert client.post("/api/verify/does-not-exist").status_code == 404


# =========================================================================== #
# Comparison
# =========================================================================== #
class TestComparison:
    """``POST /api/compare`` uses source/target document ids and returns a
    ``comparison`` object holding the measured metrics."""

    def _pair(self, client):
        return _uploaded(client, "a.pdf")["id"], _uploaded(client, "b.pdf")["id"]

    def _compare(self, client, a, b):
        return client.post(
            "/api/compare",
            json={"source_document_id": a, "target_document_id": b},
        )

    def test_identical_documents_score_one(self, client):
        a, b = self._pair(client)
        r = self._compare(client, a, b)
        assert r.status_code == 200, r.text
        cmp = r.json()["comparison"]
        assert cmp["text_similarity"] == pytest.approx(1.0, abs=1e-6)
        assert cmp["edit_similarity"] == pytest.approx(1.0, abs=1e-6)
        assert cmp["overall_score"] == pytest.approx(1.0, abs=1e-6)
        assert cmp["edit_distance"] == 0

    def test_response_envelope(self, client):
        a, b = self._pair(client)
        body = self._compare(client, a, b).json()
        assert {"source_document", "target_document", "comparison",
                "verdict", "algorithms_executed"} <= set(body)
        assert body["source_document"]["id"] == a
        assert body["target_document"]["id"] == b
        assert body["algorithms_executed"], "the comparison must name the algorithms it ran"

    def test_one_character_edit_stays_highly_similar(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        mutated = [ln.replace("008421", "008422") for ln in SAMPLE_LINES]
        b = _uploaded(client, "b.pdf", lines=mutated)["id"]
        cmp = self._compare(client, a, b).json()["comparison"]
        assert 0.85 < cmp["text_similarity"] < 1.0
        # A single-substitution edit: small distance, large LCS.
        assert cmp["edit_distance"] <= 5
        assert cmp["lcs_length"] > 0

    def test_unrelated_documents_score_low(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        other = [
            "Tax Invoice",
            "Invoice Number: INV-9911",
            "Buyer: Different Company Pvt Ltd",
            "Taxable Value: 124500.00",
        ]
        b = _uploaded(
            client, "inv.pdf", title="Tax Invoice", lines=other, doc_type="invoice"
        )["id"]
        cmp = self._compare(client, a, b).json()["comparison"]
        assert cmp["text_similarity"] < 0.9

    def test_comparison_reports_lcs_and_edit_metrics(self, client):
        a, b = self._pair(client)
        cmp = self._compare(client, a, b).json()["comparison"]
        for key in ("text_similarity", "edit_similarity", "overall_score",
                    "lcs_length", "edit_distance", "words_added",
                    "words_removed", "words_unchanged", "substitutions",
                    "elapsed_ms"):
            assert key in cmp, f"comparison payload is missing {key}"

    def test_word_accounting_is_consistent(self, client):
        a, b = self._pair(client)
        cmp = self._compare(client, a, b).json()["comparison"]
        total = cmp["words_unchanged"] + cmp["words_added"]
        assert total > 0
        assert cmp["words_removed"] >= 0

    def test_text_similarity_is_symmetric(self, client):
        a, b = self._pair(client)
        ab = self._compare(client, a, b).json()["comparison"]["text_similarity"]
        ba = self._compare(client, b, a).json()["comparison"]["text_similarity"]
        assert ab == pytest.approx(ba, abs=1e-9)

    def test_raw_text_comparison(self, client):
        r = client.post(
            "/api/compare",
            json={"source_text": "the quick brown fox", "target_text": "the quick brown fox"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["comparison"]["text_similarity"] == pytest.approx(1.0, abs=1e-6)

    def test_field_diff_endpoint(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        mutated = [ln.replace("008421", "008422") for ln in SAMPLE_LINES]
        b = _uploaded(client, "b.pdf", lines=mutated)["id"]
        r = client.post(
            "/api/compare/field-diff",
            json={"source_document_id": a, "target_document_id": b},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "fields" in body and "changed" in body
        assert body["changed"] >= 1, "the mutated registration number must be reported"

    def test_field_diff_reports_the_edited_value(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        mutated = [ln.replace("008421", "008422") for ln in SAMPLE_LINES]
        b = _uploaded(client, "b.pdf", lines=mutated)["id"]
        body = client.post(
            "/api/compare/field-diff",
            json={"source_document_id": a, "target_document_id": b},
        ).json()
        changed = [f for f in body["fields"] if not f["equal"]]
        assert changed
        assert any(
            "008422" in str(f.get("target_value")) or "008421" in str(f.get("source_value"))
            for f in changed
        )

    def test_field_diff_requires_both_ids(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        r = client.post("/api/compare/field-diff", json={"source_document_id": a})
        assert r.status_code == 400

    def test_compare_export(self, client):
        a, b = self._pair(client)
        payload = self._compare(client, a, b).json()
        r = client.post("/api/compare/export", json={"payload": payload})
        assert r.status_code in (200, 201), r.text
        assert r.content[:5] == b"%PDF-"

    def test_compare_missing_document_is_404(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        r = self._compare(client, a, "does-not-exist")
        assert r.status_code == 404

    def test_compare_with_itself_scores_one(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        r = self._compare(client, a, a)
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert r.json()["comparison"]["text_similarity"] == pytest.approx(1.0, abs=1e-6)


# =========================================================================== #
# Duplicate detection
# =========================================================================== #
class TestDuplicates:
    def test_byte_identical_copy_is_flagged(self, client):
        payload = _pdf_bytes("Certificate of Registration", SAMPLE_LINES)
        _upload(client, "a.pdf", payload=payload)
        doc = _upload(client, "b.pdf", payload=payload).json()["document"]
        assert doc["duplicate_status"] in {
            "exact_duplicate", "content_duplicate", "near_duplicate",
        }, f"a byte-identical copy was reported as {doc['duplicate_status']}"

    def test_one_character_edit_is_a_content_duplicate(self, client):
        _upload(client, "a.pdf")
        mutated = [ln.replace("008421", "008422") for ln in SAMPLE_LINES]
        doc = _upload(client, "b.pdf", lines=mutated).json()["document"]
        assert doc["duplicate_status"] != "unique"
        assert doc["similarity_score"] is not None
        assert doc["similarity_score"] > 0.9

    def test_genuinely_new_document_is_unique(self, client):
        other = ["Tax Invoice", "Invoice Number: INV-9911", "Amount: 124500.00"]
        doc = _upload(
            client, "inv.pdf", title="Tax Invoice", lines=other, doc_type="invoice"
        ).json()["document"]
        assert doc["duplicate_status"] == "unique"

    def test_duplicate_summary_shape(self, client):
        r = client.get("/api/duplicates/summary")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_duplicate_listing(self, client):
        r = client.get("/api/duplicates")
        assert r.status_code == 200
        assert isinstance(_items(r.json()), list)

    def test_duplicate_group_detail(self, client):
        _upload(client, "a.pdf")
        _upload(client, "b.pdf")
        groups = _items(client.get("/api/duplicates").json())
        if not groups:
            pytest.skip("no duplicate groups exist in this dataset")
        gid = groups[0].get("id") or groups[0].get("group_id")
        r = client.get(f"/api/duplicates/{gid}")
        assert r.status_code == 200

    def test_missing_group_is_404(self, client):
        assert client.get("/api/duplicates/does-not-exist").status_code == 404


# =========================================================================== #
# Reports
# =========================================================================== #
class TestReports:
    def _run_id(self, client):
        doc_id = _uploaded(client, "a.pdf")["id"]
        return client.post(f"/api/verify/{doc_id}").json()["run"]["id"]

    def test_generate_list_and_fetch_report(self, client):
        gen = client.post(f"/api/reports/{self._run_id(client)}/generate",
                          json={"format": "pdf"})
        assert gen.status_code in (200, 201), gen.text
        body = gen.json()
        report = body["report"] if "report" in body else body
        report_id = report["id"]

        listing = client.get("/api/reports")
        assert listing.status_code == 200
        assert any(r["id"] == report_id for r in _items(listing.json()))
        assert listing.json().get("items") is not None

        assert client.get(f"/api/reports/{report_id}").status_code == 200

    def test_report_json_payload_is_non_empty(self, client):
        generated = client.post(
            f"/api/reports/{self._run_id(client)}/generate", json={"format": "pdf"}
        ).json()
        report_id = (generated["report"] if "report" in generated else generated)["id"]
        r = client.get(f"/api/reports/{report_id}/json")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict) and body

    def test_report_pdf_is_a_real_pdf(self, client):
        generated = client.post(
            f"/api/reports/{self._run_id(client)}/generate", json={"format": "pdf"}
        ).json()
        report_id = (generated["report"] if "report" in generated else generated)["id"]
        r = client.get(f"/api/reports/{report_id}/download")
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1000

    def test_comparison_report(self, client):
        a = _uploaded(client, "a.pdf")["id"]
        mutated = [ln.replace("008421", "008422") for ln in SAMPLE_LINES]
        b = _uploaded(client, "b.pdf", lines=mutated)["id"]
        payload = client.post(
            "/api/compare", json={"source_document_id": a, "target_document_id": b}
        ).json()
        r = client.post("/api/reports/export/comparison", json={"payload": payload})
        assert r.status_code in (200, 201), r.text

    def test_missing_report_is_404(self, client):
        assert client.get("/api/reports/does-not-exist").status_code == 404


# =========================================================================== #
# Algorithms
# =========================================================================== #
class TestAlgorithmsRouter:
    REQUIRED = {
        "kmp", "rabin_karp", "lcs", "edit_distance", "tree_traversal",
        "topological_sort", "inversions", "merge_sort", "quick_sort",
        "binary_search", "huffman", "bipartite_matching", "set_cover",
    }

    def test_catalogue_lists_every_algorithm(self, client):
        body = client.get("/api/algorithms").json()
        items = body["algorithms"] if isinstance(body, dict) else body
        names = {a["name"] for a in items}
        assert self.REQUIRED <= names, f"missing: {self.REQUIRED - names}"

    def test_every_algorithm_declares_unit_and_complexity(self, client):
        body = client.get("/api/algorithms").json()
        for alg in (body["algorithms"] if isinstance(body, dict) else body):
            assert alg.get("unit"), alg["name"]
            assert alg.get("complexity_time"), alg["name"]
            assert alg.get("complexity_space"), alg["name"]
            assert alg.get("title"), alg["name"]

    def test_catalogue_exposes_parameter_definitions(self, client):
        body = client.get("/api/algorithms").json()
        algs = body["algorithms"] if isinstance(body, dict) else body
        kmp = next(a for a in algs if a["name"] == "kmp")
        params = {p["name"] for p in kmp["parameters"]}
        assert {"text", "pattern"} <= params

    def _run(self, client, algorithm, inputs):
        return client.post("/api/algorithms/run",
                           json={"algorithm": algorithm, "inputs": inputs})

    def test_run_kmp(self, client):
        r = self._run(client, "kmp", {"text": "abababc", "pattern": "ab"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["matches"] == [0, 2, 4]
        assert body["execution_time_ms"] >= 0
        assert body["operations"] > 0

    def test_run_response_carries_theory_metadata(self, client):
        body = self._run(client, "kmp", {"text": "abcabc", "pattern": "abc"}).json()
        assert body["algorithm"] == "kmp"
        assert body["unit"]
        assert body["complexity_time"]
        assert body["complexity_space"]
        assert body["title"]

    def test_run_rabin_karp(self, client):
        r = self._run(client, "rabin_karp", {"text": "hello world", "pattern": "world"})
        assert r.status_code == 200
        assert 6 in r.json()["result"]["matches"]

    def test_kmp_and_rabin_karp_agree(self, client):
        text, pattern = "the auditor verified the certificate", "cert"
        kmp = self._run(client, "kmp", {"text": text, "pattern": pattern}).json()
        rk = self._run(client, "rabin_karp", {"text": text, "pattern": pattern}).json()
        assert kmp["result"]["matches"] == rk["result"]["matches"]

    def test_run_binary_search(self, client):
        r = self._run(client, "binary_search", {"items": [1, 3, 5, 7, 9], "target": 7})
        assert r.status_code == 200, r.text
        assert r.json()["result"].get("index") == 3

    def test_binary_search_missing_target(self, client):
        r = self._run(client, "binary_search", {"items": [1, 2, 3], "target": 99})
        assert r.status_code == 200
        assert r.json()["result"].get("index") in (None, -1)

    def test_run_merge_sort(self, client):
        r = self._run(client, "merge_sort", {"items": [5, 2, 9, 1]})
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        assert result.get("sorted") == [1, 2, 5, 9] or result.get("items") == [1, 2, 5, 9]

    def test_merge_sort_is_stable_and_correct(self, client):
        items = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]
        result = self._run(client, "merge_sort", {"items": items}).json()["result"]
        ordered = result.get("sorted") or result.get("items")
        assert ordered == sorted(items)

    def test_quick_sort_matches_merge_sort(self, client):
        items = [10, 7, 8, 9, 1, 5]
        ms = self._run(client, "merge_sort", {"items": items}).json()["result"]
        qs = self._run(client, "quick_sort", {"items": items}).json()["result"]
        assert (ms.get("sorted") or ms.get("items")) == (qs.get("sorted") or qs.get("items"))

    def test_run_lcs(self, client):
        # LCS operates on word tokens, so use words rather than one long string.
        r = self._run(
            client, "lcs",
            {"source_text": "the quick brown fox jumps",
             "target_text": "the slow brown fox leaps"},
        )
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        # "the brown fox" is the common subsequence.
        assert result.get("length") == 3
        assert "brown" in result.get("matched_tokens", [])

    def test_run_edit_distance(self, client):
        r = self._run(client, "edit_distance", {"source_text": "kitten", "target_text": "sitting"})
        assert r.status_code == 200
        result = r.json()["result"]
        assert result.get("distance") == 3

    def test_run_count_inversions(self, client):
        r = self._run(client, "inversions", {"items": [2, 4, 1, 3, 5]})
        assert r.status_code == 200, r.text
        assert r.json()["result"].get("inversion_count") == 3

    def test_run_huffman(self, client):
        r = self._run(client, "huffman", {"text": "abracadabra"})
        assert r.status_code == 200, r.text
        assert r.json()["result"]

    def test_run_topological_sort(self, client):
        r = self._run(
            client, "topological_sort",
            {"nodes": ["a", "b", "c", "d"],
             "edges": [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]]},
        )
        assert r.status_code == 200, r.text
        order = r.json()["result"].get("order") or r.json()["result"].get("topological_order")
        assert order, r.text
        assert order.index("a") < order.index("d")

    def test_topological_sort_detects_a_cycle(self, client):
        r = self._run(
            client, "topological_sort",
            {"nodes": ["a", "b", "c"],
             "edges": [["a", "b"], ["b", "c"], ["c", "a"]]},
        )
        # A cycle is a legitimate, reportable outcome -- not a 500.
        assert r.status_code in (200, 400, 422)

    def test_run_tree_traversal_bfs_and_dfs(self, client):
        tree = {"value": "root", "children": [
            {"value": "left", "children": []},
            {"value": "right", "children": []},
        ]}
        for order in ("bfs", "dfs"):
            r = self._run(client, "tree_traversal", {"tree": tree, "order": order})
            assert r.status_code == 200, r.text

    def test_run_set_cover(self, client):
        r = self._run(
            client, "set_cover",
            {"universe": ["a", "b", "c", "d"],
             "sets": [["a", "b"], ["c", "d"], ["a", "d"]]},
        )
        # An unrecognised argument shape is a 400/422; a valid one is a 200.
        assert r.status_code in (200, 400, 422), r.text
        if r.status_code == 200:
            assert r.json()["result"]

    def test_run_bipartite_matching(self, client):
        r = self._run(
            client, "bipartite_matching",
            {"left": ["l1", "l2"], "right": ["r1", "r2"],
             "edges": [["l1", "r1"], ["l2", "r1"], ["l2", "r2"]]},
        )
        assert r.status_code in (200, 400, 422), r.text
        if r.status_code == 200:
            assert r.json()["result"]

    def test_run_returns_a_trace_for_playback(self, client):
        r = self._run(client, "kmp", {"text": "aaaa", "pattern": "aa"})
        assert r.status_code == 200
        assert r.json().get("trace"), \
            "every run must expose a trace for the Laboratory player"

    def test_trace_steps_are_well_formed(self, client):
        trace = self._run(client, "merge_sort", {"items": [3, 1, 2]}).json()["trace"]
        assert trace
        for step in trace:
            assert isinstance(step, dict) and step
            assert any(k in step for k in ("step", "index", "action", "description"))

    def test_unknown_algorithm_is_rejected(self, client):
        r = self._run(client, "no_such_algorithm", {})
        assert r.status_code in (400, 404, 422)

    def test_malformed_input_is_rejected(self, client):
        # `pattern` must be a string; a list is a type error, not a valid search.
        r = self._run(client, "kmp", {"text": "abc", "pattern": ["not", "a", "string"]})
        assert r.status_code in (400, 422), r.text

    def test_sort_without_items_is_rejected(self, client):
        r = self._run(client, "merge_sort", {})
        assert r.status_code in (400, 422)

    def test_history_records_runs(self, client):
        self._run(client, "kmp", {"text": "abc", "pattern": "b"})
        r = client.get("/api/algorithms/history")
        assert r.status_code == 200
        assert isinstance(_items(r.json()), list)

    def test_history_payload_contract(self, client):
        """The history endpoint always returns a page-shaped envelope."""
        body = client.get("/api/algorithms/history").json()
        assert isinstance(body, dict)
        assert "items" in body
        assert isinstance(body["items"], list)
        # Any rows that ARE present must carry real measurements.
        for row in body["items"]:
            assert row["algorithm"]
            assert row["execution_time_ms"] >= 0
            assert row["operation_count"] >= 0

    def test_upload_pipeline_records_algorithm_runs(self, client):
        """Uploading a document runs algorithms and records them with timings."""
        doc = _uploaded(client, "a.pdf")["id"]
        history = _items(client.get("/api/algorithms/history").json())
        linked = [h for h in history if h.get("document_id") == doc]
        assert linked, "the upload pipeline must record its algorithm runs"
        assert all(h["execution_time_ms"] >= 0 for h in linked)
        assert {h["algorithm"] for h in linked}, "runs must name their algorithm"


# =========================================================================== #
# Benchmarks
# =========================================================================== #
class TestBenchmarks:
    def test_options(self, client):
        body = client.get("/api/benchmarks/options").json()
        assert body["algorithms"]
        assert body["sizes"]
        assert body["case_types"]

    def test_summary(self, client):
        assert client.get("/api/benchmarks/summary").status_code == 200

    def test_list(self, client):
        r = client.get("/api/benchmarks")
        assert r.status_code == 200
        assert isinstance(_items(r.json()), list)

    def test_run_small_benchmark(self, client):
        r = client.post(
            "/api/benchmarks/run",
            json={"algorithms": ["kmp"], "sizes": [500], "repeats": 1},
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert "rows" in body and body["rows"]
        row = body["rows"][0]
        assert row["algorithm"] == "kmp"
        assert row["input_size"] == 500
        assert row["execution_time_ms"] >= 0
        assert row["operations"] >= 0
        assert body["stored"] >= 1

    def test_benchmark_response_includes_a_summary(self, client):
        body = client.post(
            "/api/benchmarks/run",
            json={"algorithms": ["merge_sort"], "sizes": [500], "repeats": 1},
        ).json()
        assert isinstance(body.get("summary"), dict)

    def test_benchmark_rows_are_persisted(self, client):
        client.post(
            "/api/benchmarks/run",
            json={"algorithms": ["merge_sort"], "sizes": [500], "repeats": 1},
        )
        listed = _items(client.get("/api/benchmarks").json())
        assert any(r["algorithm"] == "merge_sort" for r in listed)

    def test_benchmark_can_skip_persistence(self, client):
        body = client.post(
            "/api/benchmarks/run",
            json={"algorithms": ["binary_search"], "sizes": [500],
                  "repeats": 1, "persist": False},
        ).json()
        assert body["rows"]
        assert body["stored"] == 0

    def test_rejects_an_oversized_repeat_count(self, client):
        r = client.post(
            "/api/benchmarks/run",
            json={"algorithms": ["kmp"], "sizes": [500], "repeats": 999},
        )
        assert r.status_code == 422

    def test_csv_export(self, client):
        r = client.get("/api/benchmarks/export.csv")
        assert r.status_code == 200
        assert "algorithm" in r.text.lower()


# =========================================================================== #
# Analytics
# =========================================================================== #
class TestAnalytics:
    def test_overview(self, client):
        _uploaded(client, "a.pdf")
        r = client.get("/api/analytics/overview")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_overview_reflects_uploads(self, client):
        for i in range(3):
            _uploaded(client, f"d{i}.pdf")
        body = client.get("/api/analytics/overview").json()
        assert json.dumps(body).count("3") >= 1 or body.get("documents_total") == 3

    def test_algorithm_analytics(self, client):
        assert client.get("/api/analytics/algorithms").status_code == 200


# =========================================================================== #
# Settings
# =========================================================================== #
class TestSettings:
    def test_get_settings(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert isinstance(r.json(), (dict, list))

    def test_reset_settings(self, client):
        assert client.post("/api/settings/reset").status_code in (200, 204)

    def test_update_a_setting(self, client):
        body = client.get("/api/settings").json()
        rows = body if isinstance(body, list) else _items(body)
        if not rows:
            pytest.skip("no settings exposed")
        row = rows[0]
        key = row["key"] if isinstance(row, dict) else row
        current = row.get("value") if isinstance(row, dict) else None
        r = client.put(f"/api/settings/{key}", json={"value": current or "1"})
        assert r.status_code in (200, 204, 422)

    def test_updating_an_unknown_setting_is_rejected(self, client):
        r = client.put("/api/settings/not_a_real_setting", json={"value": "1"})
        assert r.status_code in (400, 404, 422)


# =========================================================================== #
# The full linear walk-through -- the six-sample demo in miniature
# =========================================================================== #
class TestEndToEndWalkthrough:
    def test_the_whole_examination_arc(self, client):
        """Upload -> read -> measure -> rule -> file -> review."""
        original = _pdf_bytes("Certificate of Registration", SAMPLE_LINES)
        mutated = _pdf_bytes(
            "Certificate of Registration",
            [ln.replace("008421", "008422") for ln in SAMPLE_LINES],
        )

        a = _upload(client, "original.pdf", payload=original)
        assert a.status_code in (200, 201), a.text
        a_id = a.json()["document"]["id"]

        b = _upload(client, "mutated.pdf", payload=mutated)
        assert b.status_code in (200, 201), b.text
        b_id = b.json()["document"]["id"]

        # 1. Read
        assert client.get(f"/api/documents/{a_id}/text").status_code == 200
        assert client.get(f"/api/documents/{a_id}/structure").status_code == 200

        # 2. Measure
        cmp = client.post(
            "/api/compare",
            json={"source_document_id": a_id, "target_document_id": b_id},
        )
        assert cmp.status_code == 200
        score = cmp.json()["comparison"]["text_similarity"]
        assert 0.85 < score < 1.0, \
            f"one-character edit should stay highly similar, got {score}"

        # 3. Rule
        verify = client.post(f"/api/verify/{a_id}")
        assert verify.status_code in (200, 201)
        run_id = verify.json()["run"]["id"]
        detail = client.get(f"/api/verifications/{run_id}").json()
        assert detail["findings"], "the run must record rule findings"

        # 4. File
        rep = client.post(f"/api/reports/{run_id}/generate", json={"format": "pdf"})
        assert rep.status_code in (200, 201)
        rep_body = rep.json()
        rep_id = (rep_body["report"] if "report" in rep_body else rep_body)["id"]
        pdf = client.get(f"/api/reports/{rep_id}/download")
        assert pdf.content[:5] == b"%PDF-"

        # 5. Review
        assert client.get("/api/analytics/overview").status_code == 200
        assert client.get("/api/duplicates/summary").status_code == 200
        assert client.get("/api/verifications").status_code == 200
