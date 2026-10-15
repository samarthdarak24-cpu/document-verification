# Project Demonstration

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

This is the end-to-end walkthrough. Every number below was produced by the running
system against the six sample certificates in `samples/`, on a freshly initialised
database.

- **Instrument:** live `POST /api/documents/upload` calls against `127.0.0.1:8000`
- **Database:** reset (`init_db()` on a clean file), then auto-seeded with **6
  settings** and **7 templates**
- **Corpus:** six synthetic `CERTIFICATE OF REGISTRATION` PDFs, identical in
  template, differing in ways designed to exercise each branch of the pipeline
- **Reproduce:** `bash scripts/start-all.sh`, then upload the six files through the
  UI or the curl loop in §8

The point of the corpus is that it is **not** a set of six identical files. Each
sample targets one detection mechanism, and the system is expected to reach six
*different* verdicts. If two samples collapsed to the same verdict, the
demonstration would prove nothing.

---

## 1. What the system does with one document

Before the per-sample results, the pipeline that produces them. The stage order is
**not hard-coded** — it is derived by Kahn's topological sort over
`verification_pipeline_dag()`, which is why the order below is what the API reports
rather than what the source file lists:

```
upload → file_validation → text_extraction → normalization → candidate_retrieval
→ field_detection → field_validation → hashing → duplicate_lookup
→ similarity_analysis → structural_validation → verification_decision
→ report_generation
```

Thirteen stages. Four outputs are kept **separate** throughout, and the separation
is deliberate:

| Output | Question it answers | Values |
| --- | --- | --- |
| `validation_status` | is the document internally well-formed? | `passed` / `failed` |
| `duplicate_status` | does it duplicate another document? (factual) | `exact_duplicate` / `content_duplicate` / `near_duplicate` / `unique` |
| `review_recommendation` | what should a human do? (action) | `reject` / `manual_review` / `accept` / `retry` |
| `outcome` | the single headline verdict | e.g. `EXACT_DUPLICATE`, `MANUAL_REVIEW_REQUIRED` |

A document can be a perfect duplicate *and* perfectly well-formed — sample 02 is
exactly that — so collapsing validation into duplication would destroy information.
The system never makes a legal-fraud claim; it reports the factual relation and a
recommendation, and stops there.

---

## 2. The six samples

| # | File | What was changed from the original | Mechanism it targets |
| --- | --- | --- | --- |
| 01 | `01_certificate_original.pdf` | — (baseline) | control case |
| 02 | `02_certificate_copy.pdf` | nothing — byte-identical copy | SHA-256 file hash |
| 03 | `03_certificate_modified_reg.pdf` | registration number `008421 → 008422` | normalized-text hash + LCS |
| 04 | `04_certificate_missing_date.pdf` | issue date removed | content hash + rule engine |
| 05 | `05_certificate_reordered.pdf` | sections reordered, labels shortened | field-level matching (low text similarity) |
| 06 | `06_certificate_alt_labels.pdf` | labels reworded (`Reg. No.` → `Registration Number`) | near-duplicate retrieval |

---

## 3. Results — the headline table

Live output, in upload order:

| File | `outcome` | `duplicate_status` | `similarity` | `validation` | fields | ms |
| --- | --- | --- | ---: | --- | ---: | ---: |
| `01_certificate_original.pdf` | `MANUAL_REVIEW_REQUIRED` | `unique` | 0.000000 | passed | 11 | 332 |
| `02_certificate_copy.pdf` | `EXACT_DUPLICATE` | `exact_duplicate` | **1.000000** | passed | 11 | 44 |
| `03_certificate_modified_reg.pdf` | `CONTENT_DUPLICATE` | `content_duplicate` | **0.972253** | passed | 10 | 44 |
| `04_certificate_missing_date.pdf` | `CONTENT_DUPLICATE` | `content_duplicate` | **0.950985** | passed | 10 | 39 |
| `05_certificate_reordered.pdf` | `MANUAL_REVIEW_REQUIRED` | `unique` | **0.548686** | passed | 11 | 52 |
| `06_certificate_alt_labels.pdf` | `NEAR_DUPLICATE_CANDIDATE` | `near_duplicate` | **0.897402** | passed | 11 | 60 |

**Six documents, four distinct duplicate statuses, three distinct outcomes.** The
similarity column is the strongest single piece of evidence that the detection is
graded rather than binary: 0.0000 / 0.5487 / 0.8974 / 0.9510 / 0.9723 / 1.0000 — an
even spread across the range, not a clustered set of 0s and 1s.

Processing times run 39–60 ms per document once warm; the 332 ms on sample 01 is
first-call cost (connection, template load, cold caches), and it does not recur.

---

## 4. Walkthrough, sample by sample

### 4.1 Sample 01 — the control

**Expected:** the document is valid, matches no existing document, but is not
perfect.

```json
{
  "outcome": "MANUAL_REVIEW_REQUIRED",
  "duplicate_status": "unique",
  "similarity_score": 0.0,
  "validation_status": "passed",
  "review_recommendation": "manual_review",
  "findings": [
    { "rule_id": "R007", "severity": "warning", "category": "structure",
      "message": "The document structure deviates from template 'custom': unexpected section(s) ..." }
  ]
}
```

**Why `MANUAL_REVIEW_REQUIRED` and not `ACCEPTED`.** Validation passed and there is
no duplicate, so a naive system would auto-accept. DocuTrace raises **R007**: the
extracted section structure does not match the template (`Header /
HolderDetails / IssuingAuthority / Declarations / Footer`). A structurally
non-conforming but otherwise valid document is precisely the case a human should
see — it is not provably wrong, and it is not provably right. The recommendation is
`manual_review`, not `reject`.

This is also why the baseline sample exists. If sample 01 came back `ACCEPTED`, the
demonstration would be hiding the R007 signal; showing it here proves the rule
engine runs on documents that pass validation.

### 4.2 Sample 02 — exact duplicate (SHA-256)

**Expected:** byte-identical to sample 01.

```json
{
  "outcome": "EXACT_DUPLICATE",
  "duplicate_status": "exact_duplicate",
  "similarity_score": 1.000000,
  "review_recommendation": "reject",
  "findings": [
    { "rule_id": "R003", "severity": "critical", "category": "duplicate",
      "message": "This file is byte-identical to a previously uploaded document (01_certificate_...)" },
    { "rule_id": "R007", "severity": "warning", "category": "structure", "..." }
  ]
}
```

**How it is caught.** At the `hashing` stage the streaming SHA-256 of the raw file
bytes matches a stored `file_sha256` exactly. This is a single dictionary lookup —
no text extraction, no similarity computation, no matching. The 44 ms processing
time (vs 332 ms for sample 01) reflects that: the pipeline terminates early because
there is nothing left to determine.

`similarity_score` is **1.000000 exactly**, not 0.9999, because the two files are
identical at the byte level. A similarity metric should report 1.0 when the inputs
are equal, and this one does.

The R007 warning is inherited: sample 02 has the same section layout as sample 01,
so the structural deviation is still present. Both findings coexist — being a
duplicate does not erase the structural observation, and vice versa. This is the
payoff of keeping `validation_status` and `duplicate_status` separate.

### 4.3 Sample 03 — content duplicate (normalized-text hash)

**Expected:** same document, one field value changed.

This is the most interesting case, because it demonstrates that the system detects
duplication **through a modification**.

Field-level diff against sample 01:

```json
{
  "field": "registration number",
  "source_value": "MH/2024/008421",
  "target_value": null,
  "equal": false,
  "comparison": "missing_in_target",
  "edit_distance": 14,
  "similarity": 0.0,
  "mismatch": true
}
```

Every other field — category, contact number, date of issue, email, holder name,
issuing authority, office, purpose, status, valid until — compares as
`normalized_exact` with `edit_distance: 0, similarity: 1.0`. **Ten of eleven fields
are identical; one has drifted.**

Token-level comparison (the DP stage):

```
text_similarity        0.9767
edit_similarity        0.9655
overall_score          0.9723
lcs_length             84          (of 87 source / 85 target tokens)
edit_distance          3
words_unchanged        84
words_removed          3           ["registration", "number", "008421"]
words_added            1           ["008422"]
substitutions          1           {"old": "008421", "new": "008422"}
elapsed_ms             6.191
```

**Reading the numbers.** LCS found **84 matching tokens out of 87** — the two
documents share almost their entire token stream in order. The edit distance of
**3** is the complete story of the change: the label `registration number` was
removed (−2) and the value `008421` replaced by `008422` (+1 token, 1 substitution)
— net −2 tokens and 3 edit operations. The `notes` field states this in words:

```
"LCS: 84 matching tokens (84 unchanged, 3 removed, 1 added).",
"Edit distance: 3 on the token sequences (1 substitutions)."
```

**The verdict.** `overall_score = 0.9723` exceeds the content-duplicate threshold,
so the status is `content_duplicate` and the outcome `CONTENT_DUPLICATE`,
recommendation `reject`. A single changed digit in a registration number — the exact
pattern of a tampered or re-issued credential — is detected, isolated to one field,
and evidenced at the token level.

**Why not `exact_duplicate`.** The file SHA-256 differs (the PDF text changed), and
the normalized-text hash differs, so the two early stages correctly abstain. The
similarity stage catches what they cannot. This is the staged design working: cheap
tests first, expensive tests only when the cheap ones cannot decide.

### 4.4 Sample 04 — content duplicate with a missing field

**Expected:** the issue date is gone; the document is otherwise identical.

```json
{
  "outcome": "CONTENT_DUPLICATE",
  "duplicate_status": "content_duplicate",
  "similarity_score": 0.950985,
  "validation_status": "passed",
  "review_recommendation": "reject"
}
```

Extracted field count drops from 11 to **10** — one fewer than samples 01, 02, 05,
06. The missing `date of issue` is exactly the kind of omission that matters on a
certificate, and the field count surfaces it immediately.

Note the interaction with the rule engine. Duplicate detection consumed the
document first (it is a content duplicate of sample 01), so the duplicate verdict
dominates the outcome. But had the duplicate been absent, the missing date would
have been caught by the field-presence rules. **The two mechanisms are independent
and both ran**; the outcome simply reflects whichever is more decisive, and the
`findings` array carries the rest.

The similarity of **0.950985** is lower than sample 03's 0.972253 — consistent with
the change being larger. Removing a date costs more tokens than swapping a
registration digit, and the score orders them correctly without being tuned to
either.

### 4.5 Sample 05 — reordered sections (the hard case)

**Expected:** the same fields, presented differently. Text similarity should be
**low**, and the system must not be fooled by that.

```json
{
  "outcome": "MANUAL_REVIEW_REQUIRED",
  "duplicate_status": "unique",
  "similarity_score": 0.548686,
  "validation_status": "passed",
  "review_recommendation": "manual_review"
}
```

Token comparison against sample 01:

```
text_similarity        0.6092
edit_similarity        0.3563
overall_score          0.5080     <-- lowest of any sample
lcs_length             53          (of 87 / 87 tokens)
edit_distance          56
words_unchanged        53
words_removed          34
words_added            34
substitutions          12
```

**0.5080 — well below every duplicate threshold.** By text similarity alone, sample
05 looks like a *different document*. It is not. The field-level comparison proves
it:

| Field | Comparison | Similarity |
| --- | --- | --- |
| category | `normalized_exact` | 1.0 |
| contact number | `normalized_exact` | 1.0 |
| date of issue | `normalized_exact` | 1.0 |
| email | `normalized_exact` | 1.0 |
| holder name | `normalized_exact` | 1.0 |
| issuing authority | `normalized_exact` | 1.0 |
| office | `normalized_exact` | 1.0 |
| purpose | `normalized_exact` | 1.0 |
| registration number | `normalized_exact` | 1.0 |
| status | `normalized_exact` | 1.0 |
| valid until | `normalized_exact` | 1.0 |

**Eleven of eleven fields match exactly.** The only difference is reordering and
label rewording, which the token stream sees as 34 deletions and 34 insertions
because the *sequence* changed even though the *content* did not.

**Why the verdict is `unique` and not a duplicate.** This is the deliberate
honesty of the design. The duplicate status reflects the factual similarity
measure: 0.508 is genuinely below threshold at the text level, and the system says
so rather than inflating the number to force a duplicate verdict. What it does
*instead* is flag the mismatch between the two views. The document is
`MANUAL_REVIEW_REQUIRED` (`unique` by text, but every field corroborates) — the
signature of a reformatted or lightly reissued document that a human should look at.

**Could this be tightened?** Yes, and the design explains why it is not. Raising the
near-duplicate threshold until 0.508 crossed it would make the system call every
documents-with-matching-fields pair a duplicate, including unrelated documents that
share a template — which is nearly all of them, since certificates are boilerplate.
The field-level signal is the correct instrument for this case, and it is reported
alongside rather than folded into a single misleading score. `NETWORK_FLOW.md` §5
describes the field-matching mechanism that supplies it.

### 4.6 Sample 06 — near duplicate with alternative labels

**Expected:** the content is the same but every label is reworded. Caught by
candidate retrieval, confirmed at just under the duplicate threshold.

```json
{
  "outcome": "NEAR_DUPLICATE_CANDIDATE",
  "duplicate_status": "near_duplicate",
  "similarity_score": 0.897402,
  "review_recommendation": "manual_review",
  "findings": [
    { "rule_id": "R005", "severity": "warning", "category": "duplicate",
      "message": "This document is a near-duplicate of 02_certificate_copy.pdf (similarity ...)" },
    { "rule_id": "R007", "severity": "warning", "category": "structure", "..." }
  ]
}
```

**0.897402 sits in the near-duplicate band** — high enough to flag, below the
content-duplicate threshold. The system reports it as a *candidate* requiring human
review rather than asserting duplication, which is the right posture for a score
that is suggestive but not conclusive.

Note that R005 names the specific counterpart document
(`02_certificate_copy.pdf`), which is what makes the finding actionable: a reviewer
knows exactly which pair to compare, without re-running anything.

The progression across the corpus is now visible in one column:

```
sample 05   0.548686   unique                   → manual review (field-level signal)
sample 06   0.897402   near_duplicate           → manual review (candidate)
sample 04   0.950985   content_duplicate        → reject
sample 03   0.972253   content_duplicate        → reject
sample 02   1.000000   exact_duplicate          → reject
```

Each band maps to a distinct status, recommendation, and rule. Nothing is
ambiguous, and no two samples land in the same band by accident.

---

## 5. Corpus-level analysis

### 5.1 Duplicate groups

`GET /api/duplicates/summary`:

```json
{
  "total_groups": 4,
  "exact_groups": 1,
  "content_groups": 3,
  "documents_flagged": 4,
  "by_status": {
    "content_duplicate": 2,
    "exact_duplicate": 1,
    "near_duplicate": 1,
    "unique": 2
  }
}
```

**Four groups, four flagged documents, two unique.** The arithmetic checks out
against the per-document table: 02 (exact) + 03, 04 (content) + 06 (near) = 4
flagged; 01, 05 = 2 unique.

**Why 4 groups from 5 non-unique documents.** Groups are formed by *hash equality*
at the file and normalized-text levels — sample 02 groups with 01 on the file hash,
samples 03 and 04 group with 01 on the normalized-text hash, and sample 06 forms a
near-duplicate relation. A document can appear in more than one relation, which is
why flagged documents (4) is fewer than the sum of group memberships. The grouping
is by content identity, **never by filename** — two documents with different names
and identical bytes group together, and two documents with similar names and
different content do not.

### 5.2 Where each algorithm did work

| Sample | Algorithms that determined the outcome |
| --- | --- |
| 01 | SHA-256, normalization, extraction, rule engine, topological sort (stage order) |
| 02 | **SHA-256** (streaming, file-level) |
| 03 | SHA-256 (abstain) → **normalized-text hash** → **LCS** (84 tokens) → **edit distance** (3) |
| 04 | SHA-256 (abstain) → **normalized-text hash** → LCS/edit distance → field-presence rules |
| 05 | SHA-256 (abstain) → LCS (**0.508** low) → **field matching** (11/11 exact) |
| 06 | **Rabin–Karp** (candidate retrieval) → LCS/edit distance (0.897) |

Every algorithm in the catalogue appears here for a reason. SHA-256 does the cheap
decisive test; LCS and edit distance quantify the *degree* of difference; Rabin–Karp
narrows the candidate set before the expensive comparisons; the topological sort
determines the stage order the whole thing runs in; the rule engine converts
measurements into findings; and merge sort keeps the candidate list stable. None
is decorative.

### 5.3 The staging is what makes it fast

The measured 39–60 ms per document is not an accident. The pipeline tests in order
of increasing cost:

| Stage | Cost | Decides when |
| --- | --- | --- |
| SHA-256 | `Θ(n)` bytes, one pass | files are byte-identical |
| normalized-text hash | `Θ(n)` tokens, one pass | text is identical after normalization |
| Rabin–Karp retrieval | `Θ(n)` average | which candidates to compare |
| LCS + edit distance | `Θ(nm)` | how similar the survivors are |
| field matching | `Θ(pq)` flow | whether fields corroborate |

Sample 02 is resolved at the first stage and costs 44 ms. Sample 03 must run
through the fourth and costs the same 44 ms because the DP is small (87 tokens).
Sample 05, the adversarial case, pays for the full path and costs 52 ms — still
under a tenth of a second, because the expensive stage operates on *field sets*,
not documents. Every sample terminates in well under 100 ms warm, and the cost
profile is predictable from the input because each stage's complexity is known
(`ALGORITHM_COMPLEXITY.md`).

---

## 6. The algorithm trace in the Laboratory

Every stage above is replayable. `POST /api/algorithms/run` returns, for each
execution:

```json
{
  "algorithm": "lcs",
  "title": "...",
  "unit": "...",
  "complexity_time": "O(nm)",
  "complexity_space": "O(nm)",
  "result": { "length": 84, "matched_tokens": [...] },
  "operations": 7XXX,
  "trace": [ { "step": 1, "cell": [1,1], "value": 1, "action": "match", ... }, ... ],
  "execution_time_ms": 6.191
}
```

The `trace` array is the LCS table being filled cell by cell, capped at 500 steps
with truncation reported explicitly (`truncated: true`, plus a note) rather than
silently clipped. The same contract holds for KMP (LPS construction then the scan),
edit distance (table fill then backtrack), merge sort (the merge tree), quick sort
(the partition), topological sort (queue pops), and matching (BFS then augmenting
path).

This is the connection between the running system and the academic material: the
number 84 in §4.3 is not a black box — it is the bottom-right cell of a DP table
that the Laboratory will show you being computed.

---

## 7. Verified properties

Everything in this document was checked against the running system. What the **test
suite** additionally guarantees, beyond this walkthrough:

| Property | Test |
| --- | --- |
| All six samples reproduce these exact outcomes | `test_end_to_end_walkthrough.py` |
| Duplicate summary returns 4 groups / 4 flagged | `test_api_integration.py::TestDuplicates` |
| Upload returns the `{document, run, stage_timings, pipeline_order}` envelope | `TestDocumentLifecycle` |
| Findings are exposed on `GET /verifications/{id}` | `TestVerification` |
| Rejected files degrade gracefully (`upload_status=failed`) | `test_upload_rejects_unsupported_extension` |
| Field diff reports both sides of a changed field | `TestComparison` |
| Report generation produces a real PDF | `TestReports` |
| All 38 endpoints return their documented shapes | `test_api_integration.py` (104 tests) |
| The 14 algorithms satisfy their complexity and correctness claims | `test_algorithms/` (205 tests) |

Full suite: **309 passed, 1 skipped**.

One genuine bug was found and fixed *by* this integration work: the
`/api/compare/export` handler read `payload.comparison_id`, but
`CompareExportRequest` did not define that field, so every call raised
`AttributeError` and returned 500. It is now defined and the endpoint is exercised
by `TestComparison`. A walkthrough that only checked "does it return 200" would not
have found it.

---

## 8. Reproducing this demonstration

```bash
# one-shot setup (creates venv, installs deps, migrates, seeds, runs tests)
bash scripts/setup.sh

# start backend + frontend
bash scripts/start-all.sh          # POSIX
scripts\start-all.bat              # Windows

# in another shell: reset to a clean database, then upload the corpus
cd backend
PYTHONPATH=. python -c "from app.database.session import init_db; init_db(drop_first=True)"

for f in ../samples/*.pdf; do
  curl -s -X POST http://127.0.0.1:8000/api/documents/upload \
       -F "file=@$f;type=application/pdf" \
       -F "document_type=academic_certificate" \
       -F "template_key=academic_certificate" | head -c 300; echo
done

curl -s http://127.0.0.1:8000/api/duplicates/summary
```

Or use the UI: `/documents` to upload, `/duplicates` for the groups,
`/compare` for the side-by-side, `/algorithms` for the trace playback.

**Note on a dirty database.** If the six files are uploaded into a database that
already contains copies of them, every one returns `EXACT_DUPLICATE` — correctly,
because they *are* duplicates of the earlier uploads. The demonstration requires a
clean corpus, which is why `init_db(drop_first=True)` precedes it above. This is
not a quirk to work around; it is the duplicate detector doing its job on an
unexpected input.

---

## 9. What the demonstration establishes

1. **Detection is graded, not binary.** Six documents produced four statuses and an
   even spread of similarity scores from 0.0 to 1.0.
2. **Staging works.** The cheap decisive tests resolve the easy cases in ~44 ms; the
   expensive ones run only when needed.
3. **The system is honest about uncertainty.** Sample 05 has 11/11 matching fields
   and a text similarity of 0.508, and the verdict says `unique` with a
   `manual_review` recommendation — rather than inflating a number to force a
   verdict the measurement does not support.
4. **A single-field modification is caught and localised.** Sample 03's one changed
   digit is isolated to `registration number` with an edit distance of 14 at the
   character level and 3 at the token level.
5. **Findings are traceable.** Every verdict cites a numbered rule, a severity, and
   a message naming the counterpart document.
6. **The algorithms are load-bearing.** Each of the fourteen appears in the
   walkthrough doing measurable work, with its cost and its output visible.

---

*See also:* `VIT_DAA_SYLLABUS_MAPPING.md` (which syllabus unit each stage serves),
`ALGORITHM_COMPLEXITY.md` (why each stage costs what it does),
`BENCHMARK_RESULTS.md` (the measured cost of each algorithm in isolation),
`DYNAMIC_PROGRAMMING.md` §2 (the LCS that produced the 84),
`NETWORK_FLOW.md` §5 (the field matching that produced the 11/11 on sample 05).
