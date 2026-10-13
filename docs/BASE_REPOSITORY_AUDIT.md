# Base Repository Audit — DocuTrace

**Audited repository:** https://github.com/ra-mkum-ar/SIMILAR-DOCUMENT-TEMPLATE-MATCHING-ALGORITHM
**Clone location:** `DocuTrace/` (this directory)
**Baseline preserved:** git tag `baseline-upstream` @ commit `b88a0dc` ("FINAL EDIT")
**Audit date:** 2026-10-14

---

## 1. Executive Summary

The upstream repository implements a *content-based duplicate-detection* concept for
document-matching: extract text from PDF/DOCX, compare structured business fields, and
produce a duplicate / not-duplicate verdict. The concept is directly reusable and is the
intellectual seed of DocuTrace.

However, the upstream code **cannot be reused as-is** for DocuTrace:

| Blocker | Severity | Detail |
|---|---|---|
| No license file (all rights reserved) | High | Code cannot be copied wholesale; only the documented *concepts* may be reused with attribution |
| Requires MongoDB (`motor`) | High | Prohibited by DocuTrace spec (SQLite/SQLAlchemy required) |
| Requires Groq API key (paid external LLM) | High | `os.environ["GROQ_API_KEY"]` makes the core import path fail without a paid key; DocuTrace must be deterministic and local-only |
| Requires `sentence-transformers` + `torch` | Medium | Multi-GB dependency, non-deterministic embeddings, cannot run in this environment |
| Frontend is Create-React-App + JSX | Medium | DocuTrace requires React + TypeScript + Vite |
| No local tests, no CI | Medium | `backend_test.py` targets a remote hosted deployment; cannot run locally |
| No database migrations, no persistence schema | High | No documents/verification/report storage model |
| No algorithm implementations | High | Uses `difflib` and regex only; no KMP/RK/LCS/EditDistance/tree algorithms |

**Decision:** reimplement the pipeline independently in Python/TypeScript following the
DocumentuTrace specification, reusing only *ideas* (field-comparison rule table, synthetic
sample-document generation approach) with explicit attribution (see §6).

---

## 2. Repository Structure (as cloned)

```
DocuTrace/
├── README.md                     # Extensive wiki-style documentation (concepts)
├── backend/
│   ├── server.py                 # FastAPI app (single file, 833 lines)
│   ├── fix_ai.py                 # Maintenance script (re-runs AI analysis on stored docs)
│   └── requirements.txt          # MongoDB / Groq / torch / PyPDF2 stack
├── frontend/                     # Create-React-App + craco + shadcn/ui (JSX)
│   ├── src/App.js                # Router-less tab shell
│   ├── src/components/
│   │   ├── DocumentMatcher.js    # Upload query document, list matches
│   │   ├── TemplateManager.js    # Upload template PDF/DOCX
│   │   └── MatchHistory.js       # Past match records
│   │   └── ui/…                  # ~45 shadcn/ui primitives (reusable UI patterns only)
│   ├── plugins/health-check/     # CRACO build plugins
│   └── package.json              # CRA deps, no TypeScript
├── backend_test.py               # Remote-API test script (https://docsimilarity.preview.emergentagent.com)
├── create_test_files.py          # Generates PDF/DOCX samples via reportlab + python-docx
├── test_files/                   # 5 sample PDF/DOCX documents (synthetic)
├── test_reports/iteration_1.json
├── test_result.md
├── tests/__init__.py             # Empty
└── uploads/                      # Stale upload artifacts
```

**89 files** (excluding `.git`). No `LICENSE`, no `alembic`, no `tests` with assertions,
no CI configuration, no OpenAI-style `.env` example beyond a bare `frontend/.env`.

---

## 3. Frameworks & Dependencies (actual)

**Backend (Python 3):** FastAPI 0.110, Starlette, Pydantic v2, `motor` (async MongoDB
driver), `groq` (LLM SDK), `python-dotenv`, PyPDF2, python-docx, numpy,
`sentence-transformers`, `torch` (unpinned — heavy install), `passlib`, `python-jose`,
`orjson`, `rich`, `requests`, `httpx`.

**Frontend:** Create React App (react-scripts 5), craco, Tailwind, ~45 Radix UI
packages, react-router-dom is **absent** (navigation is tab state in `App.js`).

The frontend `.env` points the API client at a hosted deployment
(`*.emergentagent.com`), not a local backend.

---

## 4. Functional Audit

### 4.1 What actually works (verified by code inspection)

1. **PDF text extraction** — `extract_text_from_pdf()` (PyPDF2): page count + per-page
   text + basic structure dict (`pages`, `page_data`). Works for text-based PDFs.
2. **DOCX extraction** — `extract_text_from_docx()` (python-docx): paragraphs, headings
   (`Heading*` styles), per-paragraph length. Works.
3. **Deterministic helpers** — `structure_score()` (page/paragraph + heading-set Jaccard)
   and `layout_score()` (density ratio), `confidence_score()` (length-ratio blend).
   Pure functions, no external calls. **The most reusable logic in the repo.**
4. **Rule scaffolding for forgery classification** — `forgery_risk_score()`,
   `classify_match()`, `generate_red_flags()`: deterministic threshold rules with the
   caveat that in the UI flow they are *overridden* by LLM output.
5. **CRUD endpoints** — `/api/templates` upload/list/delete, `/api/match/single`,
   `/api/match/batch`, `/api/match/history` (routing skeleton is sound).

### 4.2 What is broken / non-functional in this environment

1. **Server cannot start without external services.** `server.py` executes
   `os.environ["MONGO_URL"]` and `os.environ["GROQ_API_KEY"]` at import time and loads a
   SentenceTransformer at module import — the app fails to boot without MongoDB + a paid
   Groq key + a ~1 GB torch download. Instantiated `Groq(api_key=None)` also raises.
2. **Matching quality depends on the LLM.** `calculate_similarity()` asks Groq to
   *rewrite* numeric similarity scores; on API failure it falls back to numeric-only.
   Verdicts are therefore non-deterministic when the API is available.
3. **Embeddings are not verifiable.** `all-MiniLM-L6-v2` cosine similarity blended 0.7
   into the text score; model download is mandatory at import.
4. **Frontend is incomplete for DocuTrace**: tab navigation instead of routed pages, no
   upload progress, no OCR, no images, no reports, no persistence view, hardcoded remote
   API base URL.
5. **`backend_test.py` cannot run locally** (absolute URL to a hosted deployment;
   references `/app/test_files/...` container paths).
6. **`create_test_files.py`** writes to `/app/test_files/` (Linux container path) — fails
   on Windows.
7. **README drift**: documents `final_compare.py` and `wiki.md`, which do not exist in
   the repository (superseded by `server.py`).
8. **No tests were executable** — no local test runner entry point (confirmed: no
   `pytest`/`unittest` suite in repo).

### 4.3 Security/reliability issues inherited (must not be repeated)

- Filenames from clients are concatenated into storage paths (`{uuid}_{filename}`) after
  a suffix check only; no content-type sniffing, no size limits, no path canonicalization.
- CORS is `allow_origins=["*"]` with `allow_methods=["*"]`.
- Uploaded bytes are held in memory with no cap; PDF parsing has no resource limits.
- Client-supplied `file_path` is read back on delete (path traversal exposure).

---

## 5. Licensing

**No `LICENSE` file exists in the repository.** Absent an explicit license, copyright
defaults to *all rights reserved* for the author. Therefore:

- **No upstream source code is copied into DocuTrace.**
- Only *publicly documented concepts* are reused: (a) the field-comparison rule table
  from the README (§5 of upstream README: fuzzy names, exact IDs/dates, numeric
  equality of amounts), and (b) the idea of generating synthetic sample documents with
  reportlab + python-docx. Both are reimplemented from scratch.
- Attribution is recorded here and in `README.md` ("Attribution" section) and in
  `docs/DAA_ANALYSIS.md` where the comparison-rule concept is referenced.

---

## 6. Reuse & Modification Plan

| Upstream asset | Decision in DocuTrace | Rationale |
|---|---|---|
| Field-comparison rule table (fuzzy name / exact ID / numeric amount) | **Reused as concept**, reimplemented deterministically with normalized values + KMP/label search + Edit Distance | Core of the verification engine |
| `structure_score` / `layout_score` (Jaccard headings, density ratio) | Reimplemented in `structure.py` + tree-traversal structural signature | Scored by tree traversal instead of heuristics |
| PDF/DOCX extraction approach | Reimplemented with **PyMuPDF** (per spec) + python-docx; PyPDF2 dropped (unmaintained) | Spec compliance |
| Synthetic document generation | Reimplemented in `scripts/create_sample_documents.py` with Windows-safe paths | Base script wrote to `/app/...` |
| shadcn/ui frontend primitives (MIT-licensed library pattern) | Not copied; DocuTrace UI is purpose-built with Tailwind design tokens | Different stack (TS + Vite) and design language |
| Groq / sentence-transformers / MongoDB stack | **Removed entirely** | Prohibited: paid API, nondeterminism, external services |
| Remote-API test script | Replaced by local `pytest` suites against FastAPI TestClient | Spec Phase 16 |

---

## 7. Environment Test Evidence

| Check | Result |
|---|---|
| `git clone` of upstream | OK |
| Python venv created (`python 3.13.12`) | OK |
| Core backend imports (`fitz`, `docx`, `reportlab`, `cv2`, `fastapi`, `sqlalchemy`, `PIL`) | Verified in fresh venv |
| `tesseract` OCR binary | **Not installed on this machine** — OCR path is implemented but gracefully degrades; documented in README |
| Upstream test suite execution | **Not possible** (remote URL + container paths) — recorded as a defect |

---

## 8. Conclusion

The upstream repository contributes a sound *problem framing* (verify identity by
content, not appearance) and a field-rule concept, but its runtime dependencies are
incompatible with DocuTrace's constraints (no MongoDB, no paid LLM, no torch, local-only
operation, deterministic verification, full algorithm transparency). DocuTrace therefore
reuses the documented concepts with attribution and implements everything — extraction,
normalization, field validation, hashing, duplicate detection, similarity, structural
validation, verification, reporting, benchmarks, UI — independently per the master
specification.
