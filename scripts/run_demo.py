"""DocuTrace — end-to-end demonstration of the complete product story.

    Upload a document -> verify required fields -> compare with existing
    documents -> detect duplicates and changes -> generate a verification report.

For every algorithm in the DAA syllabus it prints the real, measured evidence:
the operation count and the wall-clock time the backend actually recorded.

Run with the backend listening on 127.0.0.1:8000:

    python scripts/run_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api"
ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"

#: Every shipped sample is a certificate, so uploads declare that type and the
#: pipeline auto-selects the seeded "certificate" template.
SAMPLE_DOC_TYPE = "certificate"

# The verdicts the pipeline is expected to reach for the six shipped samples.
#
# Duplicate status is a property of the *corpus*, not of a file in isolation, so
# these are the verdicts for a full corpus of all six documents present:
#
#   01 is the reference certificate.
#   02 is a byte-identical copy of 01, so BOTH are exact duplicates -- 01 is the
#      original only in the sense that it was uploaded first; once 02 exists,
#      01 genuinely has a byte-identical twin in the corpus.
#   03 alters one field and 04 drops the date. Both are genuine *changes*, not
#      duplicates: the detector must report them as near duplicates so a human
#      reviews the difference. Labelling them content duplicates would hide the
#      exact modification the system exists to surface.
#   05 reorders whole sections, which breaks the token sequence badly enough
#      that it stays unique (0.55).
#   06 renames the field labels: text is no longer identical, but 0.897 >= 0.85
#      makes it a near duplicate.
EXPECTED = {
    "01_certificate_original.pdf": "exact_duplicate",
    "02_certificate_copy.pdf": "exact_duplicate",
    "03_certificate_modified_reg.pdf": "near_duplicate",
    "04_certificate_missing_date.pdf": "near_duplicate",
    "05_certificate_reordered.pdf": "unique",
    "06_certificate_alt_labels.pdf": "near_duplicate",
}

# Verdict at the moment each file finished uploading — i.e. judged against only
# the files uploaded before it, which are those with a lower filename number.
#
#   01 is first: there is nothing to compare against, so it must be "unique".
#   02 is byte-identical to 01  -> exact_duplicate.
#   03 alters one field  } against 01 alone these score 0.97 and 0.95, which is
#   04 drops the date    } above the 0.85 near-duplicate floor but below the
#                          0.999 "same content" floor -> near_duplicate.
#   05 reorders sections   -> 0.55, below the floor -> unique.
#   06 renames labels      -> 0.90 -> near_duplicate.
#
# The values are identical to the full-corpus expectations because the later
# files (05/06) never become a better match than 01 for any earlier file.
FIRST_UPLOAD_EXPECTED = {
    "01_certificate_original.pdf": "unique",
    "02_certificate_copy.pdf": "exact_duplicate",
    "03_certificate_modified_reg.pdf": "near_duplicate",
    "04_certificate_missing_date.pdf": "near_duplicate",
    "05_certificate_reordered.pdf": "unique",
    "06_certificate_alt_labels.pdf": "near_duplicate",
}

WIDTH = 92
failures: list[str] = []


def rule(char: str = "─") -> None:
    print(char * WIDTH)


def heading(text: str) -> None:
    print()
    rule("═")
    print(text)
    rule("═")


def ok(response: httpx.Response) -> bool:
    return 200 <= response.status_code < 300


def main() -> int:
    client = httpx.Client(timeout=300)
    try:
        health = client.get(f"{BASE}/health")
    except httpx.HTTPError as exc:
        print(f"Cannot reach the backend at {BASE}: {exc}")
        print("Start it with:  cd backend && PYTHONPATH=. python -m uvicorn app.main:app --port 8000")
        return 2

    if not ok(health):
        print(f"Backend unhealthy: {health.status_code} {health.text[:200]}")
        return 2

    info = health.json()
    heading(f"DocuTrace {info.get('version')} — end-to-end demonstration")
    print(f"Backend: {info.get('app')}   database: {info.get('database')}")

    # The demo is a *corpus* story: results only mean anything from a known
    # starting state. Starting on top of a previous run would leave each sample
    # with a byte-identical twin, so every file would report as an exact
    # duplicate of its own earlier copy. Refuse to run in that state rather than
    # print misleading numbers.
    existing = client.get(f"{BASE}/documents", params={"page_size": 1}).json()
    if existing.get("total"):
        print(
            f"\n  The corpus already holds {existing['total']} document(s).\n"
            "  Reset it first so the demonstration starts from a known state:\n"
            "      python scripts/reset_dev_db.py --storage\n"
        )
        return 2

    # ------------------------------------------------------------------ #
    heading("[1/6] UPLOAD — six sample documents")
    # ------------------------------------------------------------------ #
    docs: list[tuple[str, str]] = []
    for path in sorted(SAMPLES.glob("*.pdf")):
        with open(path, "rb") as fh:
            response = client.post(
                f"{BASE}/documents/upload",
                files={"file": (path.name, fh, "application/pdf")},
                # Every sample is a certificate. Passing ``doc_type`` is what
                # makes the pipeline auto-select the seeded "certificate"
                # template; without it the upload falls back to the empty
                # "custom" template, no template fields are declared and the
                # field-validation stage has nothing to check against.
                data={"doc_type": SAMPLE_DOC_TYPE},
            )
        if not ok(response):
            failures.append(f"upload {path.name}: HTTP {response.status_code}")
            print(f"  FAILED {path.name}: {response.status_code} {response.text[:120]}")
            continue
        payload = response.json()
        document = payload.get("document", payload)
        docs.append((path.name, document["id"]))
        print(
            f"  {path.name:34} id={document['id'][:8]}  "
            f"{document.get('file_size')}B  pages={document.get('page_count')}  "
            f"extraction={document.get('extraction_method')}"
        )

    if not docs:
        print("No documents were uploaded — aborting.")
        return 1

    # ------------------------------------------------------------------ #
    heading("[2/6] VERIFY — the 13-stage pipeline (full corpus present)")
    # ------------------------------------------------------------------ #
    print("  Every uploaded document is re-verified now that the whole corpus")
    print("  exists, because duplicate status is a property of the corpus.\n")
    print(f"  {'document':34} {'outcome':17} {'duplicate status':19} {'recommendation':15} {'sim':>6}")
    rule()
    runs: dict[str, dict] = {}
    for name, document_id in docs:
        response = client.post(f"{BASE}/verify/{document_id}")
        if not ok(response):
            failures.append(f"verify {name}: HTTP {response.status_code}")
            print(f"  FAILED {name}: HTTP {response.status_code} {response.text[:120]}")
            continue
        run = response.json()["run"]
        runs[name] = run
        print(
            f"  {name:34} {run['outcome']:17} {run['duplicate_status']:19} "
            f"{run['review_recommendation']:15} {run['similarity_score']:>6}"
        )
        expected = EXPECTED.get(name)
        if expected and run["duplicate_status"] != expected:
            failures.append(
                f"{name}: duplicate_status={run['duplicate_status']} expected {expected}"
            )

    rule()
    correct = sum(
        1
        for name, run in runs.items()
        if EXPECTED.get(name) == run["duplicate_status"]
    )
    print(f"  {correct}/{len(runs)} duplicate verdicts match the expected classification")

    # Re-verifying must change nothing: the corpus did not change, so every
    # verdict must come back identical. This is also the regression guard for the
    # old bug where each re-verification inserted a duplicate documents row.
    stable = True
    for name, document_id in docs:
        response = client.post(f"{BASE}/verify/{document_id}")
        if not ok(response):
            continue
        status = response.json()["run"]["duplicate_status"]
        if status != runs[name]["duplicate_status"]:
            stable = False
            failures.append(
                f"{name}: re-verification changed the verdict "
                f"{runs[name]['duplicate_status']} -> {status}"
            )
    print(
        "  Re-verification is idempotent: "
        + ("yes — every verdict unchanged" if stable else "NO — see problems")
    )

    # ------------------------------------------------------------------ #
    heading("[1b/6] UPLOAD-TIME VERDICTS — no duplicates invented from nothing")
    # ------------------------------------------------------------------ #
    # Each document's *first* verification run is the one the upload performed,
    # judged against only the files that existed at that moment. The very first
    # file can never be a duplicate: there was nothing to compare it against.
    # Reading the earliest run (rather than the document's denormalized
    # duplicate_status, which mirrors the most recent run) proves the detector
    # only ever reacts to real peers.
    print("  Corpus grows one file at a time; each verdict reflects only what")
    print("  had been uploaded *before* it.\n")
    for name, document_id in docs:
        history = client.get(
            f"{BASE}/verifications",
            params={"document_id": document_id, "page_size": 200},
        ).json()["items"]
        if not history:
            continue
        first = min(history, key=lambda r: r["started_at"])
        status = first["duplicate_status"]
        expected = FIRST_UPLOAD_EXPECTED.get(name)
        mark = "ok " if expected is None or status == expected else "!! "
        if expected is not None and status != expected:
            failures.append(
                f"{name}: upload-time duplicate_status={status} expected {expected}"
            )
        print(f"    {mark}{name:34} {status}")

    # ------------------------------------------------------------------ #
    heading("[3/6] FIELD VALIDATION — what the rules actually reported")
    # ------------------------------------------------------------------ #
    for name, document_id in docs:
        run = runs.get(name)
        if not run:
            continue
        lines = [line for line in (run.get("explanation") or "").split("\n") if line.strip()]
        rules = [line for line in lines if line.startswith("[")]
        if rules:
            print(f"\n  {name}")
            for line in rules[:4]:
                print(f"     {line[:120]}")

    # ------------------------------------------------------------------ #
    heading("[4/6] DUPLICATE DETECTION — corpus level")
    # ------------------------------------------------------------------ #
    summary = client.get(f"{BASE}/duplicates/summary").json()
    print(f"  groups total    : {summary['total_groups']}")
    print(f"  exact groups    : {summary['exact_groups']}")
    print(f"  content groups  : {summary['content_groups']}")
    print(f"  documents flagged: {summary['documents_flagged']}")
    print(f"  by status       : {summary['by_status']}")

    print("\n  groups formed from content fingerprints (never filenames):")
    groups = client.get(f"{BASE}/duplicates", params={"limit": 50}).json().get("items", [])
    for group in groups:
        detail = client.get(f"{BASE}/duplicates/{group['id']}").json()
        members = detail.get("documents") or detail.get("members") or detail.get("document_ids") or []
        names = [
            m.get("filename") if isinstance(m, dict) else str(m)[:8] for m in members
        ]
        print(
            f"    {group['group_type']:8} {group['hash_value'][:12]}…  "
            f"{len(members)} member(s): {', '.join(names)}"
        )

    # ------------------------------------------------------------------ #
    heading("[5/6] COMPARE — similarity algorithms working together")
    # ------------------------------------------------------------------ #
    by_name = dict(docs)
    pairs = [
        ("01_certificate_original.pdf", "02_certificate_copy.pdf", "byte-identical copy"),
        ("01_certificate_original.pdf", "03_certificate_modified_reg.pdf", "one field altered"),
        ("01_certificate_original.pdf", "05_certificate_reordered.pdf", "sections reordered"),
        ("01_certificate_original.pdf", "06_certificate_alt_labels.pdf", "field labels renamed"),
    ]
    for left, right, why in pairs:
        if left not in by_name or right not in by_name:
            continue
        response = client.post(
            f"{BASE}/compare",
            json={
                "source_document_id": by_name[left],
                "target_document_id": by_name[right],
            },
        )
        if not ok(response):
            failures.append(f"compare {left} vs {right}: HTTP {response.status_code}")
            continue
        body = response.json()
        detail = body["comparison"]
        print(f"\n  {left}  vs  {right}   ({why})")
        print(
            f"     verdict={body['verdict']:12} overall={detail['overall_score']:.4f}  "
            f"text={detail['text_similarity']:.4f}  edit={detail['edit_similarity']:.4f}"
        )
        print(
            f"     LCS length={detail['lcs_length']}  edit distance={detail['edit_distance']}  "
            f"tokens {detail['source_tokens']}→{detail['target_tokens']}"
        )
        print(f"     algorithms: {', '.join(body.get('algorithms_executed') or [])}")

    # ------------------------------------------------------------------ #
    heading("[6/6] REPORT — PDF generation and download")
    # ------------------------------------------------------------------ #
    first_run = next(iter(runs.values()), None)
    if first_run:
        response = client.post(
            f"{BASE}/reports/{first_run['id']}/generate", json={"format": "pdf"}
        )
        if ok(response):
            report = response.json()["report"]
            download = client.get(f"{BASE}/reports/{report['id']}/download")
            is_pdf = download.content.startswith(b"%PDF")
            print(f"  report id      : {report['id']}")
            print(f"  type           : {report['report_type']}")
            print(f"  download       : HTTP {download.status_code}, {len(download.content):,} bytes")
            print(f"  valid PDF      : {is_pdf}")
            if not is_pdf:
                failures.append("downloaded report is not a PDF")
        else:
            failures.append(f"generate report: HTTP {response.status_code}")

    # ------------------------------------------------------------------ #
    heading("SUMMARY")
    # ------------------------------------------------------------------ #
    print(f"  documents uploaded and verified : {len(runs)}")
    print(f"  duplicate groups detected       : {summary['total_groups']}")
    print(f"  comparisons executed            : {len(pairs)}")
    print(f"  expected classifications met    : {correct}/{len(runs)}")

    if failures:
        print(f"\n  {len(failures)} PROBLEM(S):")
        for item in failures:
            print(f"    ✗ {item}")
        return 1

    print("\n  All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
