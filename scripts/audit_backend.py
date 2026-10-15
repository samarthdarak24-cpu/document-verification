"""Exhaustive backend audit for DocuTrace.

Exercises every endpoint and every DAA algorithm through the real HTTP API,
so that "does the feature actually work end to end" is answered with evidence
rather than by inspecting the UI.

Run:  python audit_backend.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api"
ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"

results: list[tuple[str, str, str, str]] = []


def check(
    label: str,
    method: str,
    path: str,
    expect: int | tuple[int, ...] = 200,
    **kw,
):
    """Call one endpoint and record pass/fail with a short evidence string."""
    url = f"{BASE}{path}"
    try:
        with httpx.Client(timeout=120.0) as client:
            started = time.perf_counter()
            r = client.request(method, url, **kw)
            ms = (time.perf_counter() - started) * 1000
    except Exception as exc:  # noqa: BLE001
        results.append((label, f"{method} {path}", "FAIL", f"exception: {exc}"))
        return None

    wanted = expect if isinstance(expect, tuple) else (expect,)
    ok = r.status_code in wanted
    body = None
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        body = r.text[:200]

    if ok:
        preview = json.dumps(body)[:110] if not isinstance(body, str) else body[:110]
        results.append((label, f"{method} {path}", "PASS", f"{r.status_code} · {ms:.0f}ms · {preview}"))
    else:
        results.append(
            (label, f"{method} {path}", "FAIL", f"{r.status_code} want {wanted} · {json.dumps(body)[:260]}")
        )
    return body


def section(name: str) -> None:
    results.append((f"── {name} " + "─" * (60 - len(name)), "", "INFO", ""))


print("=" * 100)
print("DocuTrace backend audit")
print("=" * 100)

# --------------------------------------------------------------------------- #
section("health / metadata")
# --------------------------------------------------------------------------- #
check("Health", "GET", "/health")

# --------------------------------------------------------------------------- #
section("documents")
# --------------------------------------------------------------------------- #
docs = check("List documents", "GET", "/documents", params={"limit": 100})
doc_items = (docs or {}).get("items", [])
print(f"\n  → {len(doc_items)} documents present\n")

if not doc_items:
    # Upload one sample so the rest of the audit has real data to work with.
    samples = sorted(SAMPLES.glob("*.pdf"))
    if samples:
        with open(samples[0], "rb") as fh:
            check(
                "Upload sample (seeding)",
                "POST",
                "/documents/upload",
                files={"file": (samples[0].name, fh, "application/pdf")},
            )
        docs = check("List documents (after seed)", "GET", "/documents", params={"limit": 100})
        doc_items = (docs or {}).get("items", [])

target = doc_items[-1] if doc_items else None
doc_id = target["id"] if target else None

if doc_id:
    check("Document detail", "GET", f"/documents/{doc_id}")
    check("Document text", "GET", f"/documents/{doc_id}/text")
    check("Document structure", "GET", f"/documents/{doc_id}/structure")
    check("Document preview", "GET", f"/documents/{doc_id}/preview")
    check("Document download", "GET", f"/documents/{doc_id}/download")
    check("Document detail 404", "GET", "/documents/does-not-exist", expect=404)
else:
    results.append(("Document sub-resources", "", "FAIL", "no document available to test against"))

# --------------------------------------------------------------------------- #
section("verification pipeline (the core feature)")
# --------------------------------------------------------------------------- #
verify_body = None
run = None
if doc_id:
    verify_body = check("Verify document (full pipeline)", "POST", f"/verify/{doc_id}")
    # The endpoint returns { document, run, warnings }.
    run = (verify_body or {}).get("run") if isinstance(verify_body, dict) else None
    if run:
        print()
        print("  ── pipeline verdicts (run) ──")
        for key in (
            "outcome",
            "validation_status",
            "duplicate_status",
            "review_recommendation",
            "similarity_score",
            "processing_ms",
        ):
            print(f"     {key:24} = {run.get(key)}")
        print(f"     {'document fields':24} = {len((verify_body.get('document') or {}).get('fields', []))}")
        print(f"     {'explanation lines':24} = {(run.get('explanation') or '').count(chr(10)) + 1}")
        print(f"     {'warnings':24} = {len(verify_body.get('warnings') or [])}")
        print()
    else:
        results.append(("Verify response shape", "", "FAIL", f"no 'run' key; got {list((verify_body or {}).keys())}"))

if run and run.get("id"):
    check("Verification run detail", "GET", f"/verifications/{run['id']}")

check("List verifications", "GET", "/verifications", params={"limit": 10})
if doc_id:
    check("List verifications (by document)", "GET", "/verifications", params={"document_id": doc_id, "limit": 10})

# --------------------------------------------------------------------------- #
section("comparison / similarity")
# --------------------------------------------------------------------------- #
if len(doc_items) >= 2:
    left, right = doc_items[-1]["id"], doc_items[-2]["id"]
    cmp_body = check(
        "Compare two documents",
        "POST",
        "/compare",
        json={"source_document_id": left, "target_document_id": right},
    )
    check(
        "Field diff",
        "POST",
        "/compare/field-diff",
        json={"source_document_id": left, "target_document_id": right},
    )
    # /compare/export renders a PDF from a comparison that was already computed,
    # so it is fed the entire /compare response envelope (a CompareResponse).
    if isinstance(cmp_body, dict) and cmp_body.get("comparison"):
        export = check(
            "Compare export (PDF from computed comparison)",
            "POST",
            "/compare/export",
            json={"payload": cmp_body, "format": "pdf"},
        )
        is_pdf = isinstance(export, str) and export.startswith("%PDF")
        results.append(
            (
                "Compare export returns real PDF",
                "",
                "PASS" if is_pdf else "FAIL",
                f"body starts with {str(export)[:12]!r}",
            )
        )
    else:
        results.append(
            (
                "Compare export",
                "",
                "FAIL",
                f"/compare returned no comparison object: {list((cmp_body or {}).keys())}",
            )
        )
    check(
        "Compare with missing ids (should 400)",
        "POST",
        "/compare",
        json={},
        expect=(400, 422),
    )
else:
    results.append(("Compare", "", "FAIL", "needs at least 2 documents"))

# --------------------------------------------------------------------------- #
section("duplicate detection")
# --------------------------------------------------------------------------- #
dup = check("Duplicate groups", "GET", "/duplicates", params={"limit": 50})
check("Duplicate summary", "GET", "/duplicates/summary")
groups = (dup or {}).get("items", [])
if groups:
    gid = groups[0].get("id") or groups[0].get("group_id")
    if gid:
        check("Duplicate group detail", "GET", f"/duplicates/{gid}")
    members = groups[0].get("document_ids") or []
    detail = check("Duplicate group detail", "GET", f"/duplicates/{gid}") if gid else None
    member_list = (
        (detail or {}).get("documents")
        or (detail or {}).get("members")
        or (detail or {}).get("document_ids")
        or members
    )
    results.append(
        (
            "Duplicate group membership",
            "",
            "PASS" if member_list else "FAIL",
            f"first group resolves to {len(member_list)} member document(s)",
        )
    )

# --------------------------------------------------------------------------- #
section("templates")
# --------------------------------------------------------------------------- #
tpls = check("List templates", "GET", "/templates")
tpl_items = (tpls or {}).get("items", [])
if tpl_items:
    tid = tpl_items[0]["id"]
    check("Template detail", "GET", f"/templates/{tid}")

    created = check(
        "Create template",
        "POST",
        "/templates",
        json={
            "name": "audit_temp_template",
            "category": "administrative",
            "description": "Created by audit_backend.py",
            "required_fields": ["applicant_name"],
            "field_definitions": [
                {
                    "name": "applicant_name",
                    "label": "Applicant Name",
                    "type": "string",
                    "required": True,
                    "patterns": ["Name\\s*:\\s*(.+)"],
                }
            ],
            "section_order": ["header", "body"],
        },
        expect=(200, 201),
    )
    new_id = (created or {}).get("id")
    if new_id:
        check(
            "Update template",
            "PUT",
            f"/templates/{new_id}",
            json={"description": "Updated by audit_backend.py"},
        )
        check("Delete template", "DELETE", f"/templates/{new_id}")

# --------------------------------------------------------------------------- #
section("algorithms — every registered algorithm run live")
# --------------------------------------------------------------------------- #
algos = check("List algorithms", "GET", "/algorithms")
alg_list = (algos or {}).get("algorithms", [])
print(f"\n  → {len(alg_list)} algorithms registered\n")

# Payloads must match the declared parameter names EXACTLY — the backend
# rejects undeclared keys, so these are copied from GET /algorithms.
SAMPLE_TEXT = (
    "CERTIFICATE OF REGISTRATION\n"
    "Holder Name: Ananya R. Deshmukh\n"
    "Registration Number: MH/2024/008421\n"
    "Date of Issue: 2024-04-12\n"
    "Issuing Authority: State Registrar of Societies\n"
)

PAYLOADS: dict[str, dict] = {
    "kmp": {"text": SAMPLE_TEXT, "pattern": "Ananya R. Deshmukh"},
    "rabin_karp": {"text": SAMPLE_TEXT, "pattern": "MH/2024/008421"},
    "sha256": {"text": SAMPLE_TEXT},
    "lcs": {
        "source_text": "Holder Name: Ananya R. Deshmukh",
        "target_text": "Holder Name: Ananya R. Deshmuk",
    },
    "edit_distance": {
        "source_text": "CERTIFICATE OF REGISTRATION",
        "target_text": "CERTIFICAT OF REGISTRATION",
    },
    "huffman": {"text": SAMPLE_TEXT},
    "merge_sort": {"items": [5, 2, 9, 1, 7, 3], "trace": False},
    "quick_sort": {"items": [5, 2, 9, 1, 7, 3], "trace": False},
    "binary_search": {"items": [1, 2, 3, 5, 7, 9], "target": "7", "trace": False},
    "inversions": {"items": [5, 2, 9, 1, 7, 3], "trace": False},
    "topological_sort": {
        "nodes": ["upload", "extract", "verify", "report"],
        "edges": [["upload", "extract"], ["extract", "verify"], ["verify", "report"]],
        "trace": False,
    },
    "tree_traversal": {
        "tree": [
            {"name": "HEADER", "level": 1},
            {"name": "HOLDERDETAILS", "level": 1},
            {"name": "ISSUINGAUTHORITY", "level": 1},
            {"name": "DECLARATIONS", "level": 1},
            {"name": "FOOTER", "level": 1},
        ],
        "required_sections": ["HEADER", "DECLARATIONS", "FOOTER"],
        "trace": False,
    },
    "bipartite_matching": {
        "expected_fields": ["holder_name", "registration_number", "date_of_issue"],
        "extracted_fields": ["Holder Name", "Registration Number", "Date of Issue"],
        "aliases": {},
        "similarity_threshold": 0.6,
    },
    "set_cover": {
        "requirements": ["holder_name", "registration_number", "date_of_issue", "status"],
        "rules": [
            {"name": "identity", "cost": 1, "covers": ["holder_name", "registration_number"]},
            {"name": "dates", "cost": 1, "covers": ["date_of_issue"]},
            {"name": "lifecycle", "cost": 1, "covers": ["status"]},
        ],
        "include_exhaustive": True,
    },
}


schema_by_algo = {}
try:
    spec = json.loads(httpx.get(f"{BASE}/openapi.json", timeout=30).text)
    paths = spec.get("paths", {})
    if "/api/algorithms/run" in paths:
        results.append(("OpenAPI schema", "", "PASS", "readable"))
    else:
        results.append(("OpenAPI schema", "", "INFO", "run path absent from spec"))
except Exception as exc:  # noqa: BLE001
    results.append(("OpenAPI schema", "", "INFO", f"could not read: {exc}"))

for algo in alg_list:
    name = algo["name"]
    declared = [p["name"] for p in algo.get("parameters", [])]
    payload = dict(PAYLOADS.get(name) or {})

    # Seed from declared defaults so optional params (e.g. `trace`) are present.
    for p in algo.get("parameters", []):
        if p["name"] not in payload and p.get("default") is not None:
            payload[p["name"]] = p["default"]

    missing = [p for p in declared if p not in payload]
    unexpected = [k for k in payload if k not in declared]

    try:
        body = check(
            f"Run {name}", "POST", "/algorithms/run", json={"algorithm": name, "inputs": payload}
        )
    except Exception as exc:  # noqa: BLE001
        results.append((f"Run {name}", "POST /algorithms/run", "FAIL", f"harness error: {exc}"))
        continue

    if isinstance(body, dict):
        # Prove the algorithm actually did work, not merely returned 200.
        ops = body.get("operations")
        elapsed = body.get("execution_time_ms")
        results.append(
            (
                f"Run {name} (evidence)",
                "",
                "PASS" if ops is not None else "FAIL",
                f"ops={ops} time={elapsed}ms result_keys={list((body.get('result') or {}).keys())[:6]}",
            )
        )
    elif body is not None:
        results.append((f"Run {name} (evidence)", "", "FAIL", f"non-dict body: {str(body)[:120]}"))
    if missing:
        results.append((f"Run {name} (uncovered params)", "", "FAIL", f"missing {missing}"))
    if unexpected:
        results.append((f"Run {name} (unexpected params)", "", "FAIL", f"not declared: {unexpected}"))

check("Algorithm history", "GET", "/algorithms/history", params={"limit": 10})
check(
    "Run unknown algorithm (should 4xx)",
    "POST",
    "/algorithms/run",
    json={"algorithm": "definitely_not_real", "inputs": {}},
    expect=(400, 404, 422),
)

# --------------------------------------------------------------------------- #
section("benchmarks")
# --------------------------------------------------------------------------- #
check("Benchmark options", "GET", "/benchmarks/options")
check("Benchmark rows", "GET", "/benchmarks", params={"limit": 5})
check("Benchmark summary", "GET", "/benchmarks/summary")
check("Benchmark CSV export", "GET", "/benchmarks/export.csv")

# --------------------------------------------------------------------------- #
section("reports")
# --------------------------------------------------------------------------- #
reps = check("List reports", "GET", "/reports", params={"limit": 10})
rep_items = (reps or {}).get("items", [])
if rep_items:
    rid = rep_items[0]["id"]
    check("Report detail", "GET", f"/reports/{rid}")
    check("Report JSON", "GET", f"/reports/{rid}/json")
    check("Report download", "GET", f"/reports/{rid}/download")
if run and run.get("id"):
    check(
        "Generate report (PDF)",
        "POST",
        f"/reports/{run['id']}/generate",
        json={"format": "pdf"},
        expect=(200, 201),
    )
    check(
        "Generate report (JSON)",
        "POST",
        f"/reports/{run['id']}/generate",
        json={"format": "json"},
        expect=(200, 201),
    )

# --------------------------------------------------------------------------- #
section("settings")
# --------------------------------------------------------------------------- #
settings = check("List settings", "GET", "/settings")
set_map = (settings or {}).get("settings", {}) if isinstance(settings, dict) else {}
print(f"\n  → {len(set_map)} settings groups: {', '.join(set_map)}\n")

# Write back one nested value unchanged, so we prove the PUT path works
# without mutating real configuration.
if "similarity_thresholds" in set_map:
    check(
        "Update setting (no-op write)",
        "PUT",
        "/settings/similarity_thresholds",
        json={"value": set_map["similarity_thresholds"]},
    )
if "upload_policy" in set_map:
    check(
        "Update setting (no-op write, upload_policy)",
        "PUT",
        "/settings/upload_policy",
        json={"value": set_map["upload_policy"]},
    )
check(
    "Update unknown setting (should 4xx)",
    "PUT",
    "/settings/not_a_real_key",
    json={"value": 1},
    expect=(400, 404, 422),
)

# --------------------------------------------------------------------------- #
section("analytics")
# --------------------------------------------------------------------------- #
check("Analytics overview", "GET", "/analytics/overview")
check("Analytics algorithms", "GET", "/analytics/algorithms")

# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
print()
print("=" * 100)
passed = sum(1 for _, _, s, _ in results if s == "PASS")
failed = [r for r in results if r[2] == "FAIL"]
for label, route, status, detail in results:
    if status == "INFO":
        print(f"\n{label}")
    else:
        mark = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{mark}] {label:38} {detail}")

print()
print("=" * 100)
print(f"TOTAL {passed} passed, {len(failed)} failed")
print("=" * 100)
if failed:
    print("\nFAILURES:")
    for label, route, _, detail in failed:
        print(f"  ✗ {label}\n      {route}\n      {detail}")
    sys.exit(1)
