# DocuTrace

**Intelligent Document Verification & Similarity Detection System**

DocuTrace verifies document authenticity and detects duplicates and near-duplicates
using algorithms implemented from first principles — no black boxes, no paid APIs.
Every score it reports is reproducible from the code in `backend/app/algorithms/`.

The system is complete, local, and deterministic. It runs on a laptop with no
internet connection and no external services.

---

## What it does

Upload one or more documents. DocuTrace will:

1. **Extract** text from PDF (native text layer or OCR), DOCX, PNG, and JPG.
2. **Normalise** the text (Unicode folding, whitespace, punctuation, case) into a
   canonical comparison form.
3. **Detect fields** by matching each template's field labels and value patterns
   against the extracted text using KMP and Rabin–Karp.
4. **Validate** the document against its template with a deterministic rule engine
   (R001–R008).
5. **Fingerprint** it with a streaming SHA-256 file hash and a normalized-text hash.
6. **Find duplicates** in stages: exact (hash) → content (normalized hash) →
   near-duplicate (Jaccard candidate retrieval → LCS → edit distance).
7. **Decide** an outcome (validated, duplicate, inconsistent, review required) and
   explain *which* rule and *which* measurement produced it.
8. **Report** the result as a PDF or JSON with the raw metrics attached.

Everything above is measured: execution times, operation counts, and stage
timings are recorded against every run and surfaced in the UI and the API.

---

## Architecture

```
DocuTrace/
├── backend/                  FastAPI + SQLAlchemy + SQLite
│   ├── app/
│   │   ├── algorithms/       14 DAA algorithms, implemented from scratch
│   │   ├── api/              Routers, algorithm registry, dependencies
│   │   ├── core/             Settings, security (magic bytes, safe filenames)
│   │   ├── database/         Engine, session, declarative base
│   │   ├── models/           12 SQLAlchemy models + seeded templates
│   │   ├── pipeline/         The 13-stage document processing DAG
│   │   ├── schemas/          Pydantic v2 request/response contracts
│   │   └── services/         Extraction, normalisation, similarity, rules, reports
│   ├── alembic/              Schema migrations
│   ├── scripts/              Sample-document generator
│   └── tests/                309 tests (algorithms + API integration)
├── frontend/                 React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── components/       Layout, UI primitives, UnitRunner
│       ├── hooks/            TanStack Query hooks for every endpoint
│       ├── lib/              API client, types, utils, DAA unit metadata
│       └── pages/            12 application pages
├── docs/                     Academic documentation (DAA mapping, proofs, benchmarks)
├── samples/                  Six synthetic certificate PDFs for the demo
└── scripts/                  Setup and demo helpers
```

---

## Requirements

- **Python** 3.11 or newer (3.13 tested)
- **Node.js** 20 or newer (22 tested)
- **Tesseract OCR** — *optional*. Without it, scanned PDFs and images are
  reported as unreadable rather than silently failing. Native-text PDFs and
  DOCX work fully without it.

---

## Setup on Windows

All commands are PowerShell unless stated. Run them from the repository root.

### 1. Backend

```powershell
cd backend

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

> If PowerShell blocks the activation script, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or use
> `.\.venv\Scripts\activate.bat` from `cmd.exe`.

Create the database and apply the migration:

```powershell
alembic upgrade head
```

Start the API:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API root: <http://127.0.0.1:8000>
- Interactive docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>

### 2. Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to the backend, so no CORS
configuration is needed and both servers can run unchanged.

### 3. Optional: enable OCR

Install Tesseract and make `tesseract` available on `PATH`:

```powershell
winget install UB-Mannheim.TesseractOCR
```

Then confirm the backend detects it on startup — the health output will show
`ocr_available: true`. Without Tesseract, set `OCR_ENABLED=false` in `.env` to
suppress the startup warning.

---

## Setup on macOS / Linux

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
# second terminal
cd frontend
npm install
npm run dev
```

Optional OCR: `brew install tesseract` (macOS) or
`sudo apt install tesseract-ocr` (Debian/Ubuntu).

---

## Configuration

Copy `backend/.env.example` to `backend/.env` to override any default. Every
value has a working default, so `.env` is optional.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `DocuTrace` | Application name in responses and reports |
| `VERSION` | `1.0.0` | Reported version |
| `DEBUG` | `false` | Verbose logging and SQL echo |
| `DATABASE_URL` | `sqlite:///./docutrace.db` | SQLAlchemy connection string |
| `UPLOAD_DIR` | `backend/storage/documents` | Where uploaded files are stored |
| `REPORT_DIR` | `backend/storage/reports` | Where generated reports are written |
| `MAX_UPLOAD_MB` | `25` | Per-file upload limit |
| `DP_MAX_TOKENS` | `2000` | Cap on DP input for LCS / edit distance |
| `TEXT_EXCERPT_CHARS` | `500` | Length of the stored text excerpt |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed origins |
| `OCR_ENABLED` | `true` | Master switch for OCR |
| `OCR_MIN_CHARS_PER_PAGE` | `40` | Below this, a page is retried with OCR |

---

## Running the demo

Generate six synthetic certificate PDFs that exercise every duplicate-detection
path, then upload them:

```powershell
# from the repository root
python scripts/create_sample_documents.py --outdir samples
```

| Sample | What it is | Expected outcome |
| --- | --- | --- |
| `01_certificate_original.pdf` | A well-formed certificate | Unique, validation passed |
| `02_certificate_copy.pdf` | Byte-identical copy of 01 | `EXACT_DUPLICATE` (score 1.0000) |
| `03_certificate_modified_reg.pdf` | One digit changed in the registration number | `CONTENT_DUPLICATE` (~0.97) |
| `04_certificate_missing_date.pdf` | The issue date line removed | `CONTENT_DUPLICATE`, **validation failed** |
| `05_certificate_reordered.pdf` | Same sections, different order | `INCONSISTENT_FIELDS`, reported via inversion count |
| `06_certificate_alt_labels.pdf` | Same content, different field labels | `NEAR_DUPLICATE_CANDIDATE` (~0.90) |

Upload all six through the UI at `/upload`, then open `/duplicates` to see the
groups and `/documents` to see each verdict with its supporting measurements.

---

## Testing

```powershell
cd backend
pytest                       # everything: 309 passed, 1 skipped
pytest tests/test_algorithms # 205 algorithm unit tests
pytest tests/test_api_integration.py   # 104 API integration tests
pytest -k "kmp or rabin"     # a focused subset
```

The suite is fully isolated: `tests/conftest.py` redirects `DATABASE_URL` and the
storage roots to a throwaway temp directory **before** the application's settings
object is constructed, so no test touches your development database.

Algorithm tests cross-check every implementation against a naive reference on
randomised inputs, so a "passing" test means the algorithm is actually correct —
not merely that it returned something.

Frontend:

```powershell
cd frontend
npm run typecheck   # tsc --noEmit
npm run build       # production build
```

---

## The DAA Laboratory

`/lab` exposes every algorithm with typed inputs, a step-by-step trace, and the
theoretical complexity it is expected to honour. `/performance` runs real
benchmarks across input sizes and dataset shapes and plots the measured curves
against the predicted complexity classes.

Algorithms implemented from scratch:

| Algorithm | Unit | Typical use in DocuTrace |
| --- | --- | --- |
| Topological sort (Kahn) | I | Scheduling the 13-stage pipeline DAG |
| KMP | III | Locating field labels in extracted text |
| Rabin–Karp | III | Multi-pattern field-label search |
| SHA-256 (streaming) | III | File and normalized-text fingerprints |
| Merge sort | II | Ranking similarity candidates (stable) |
| Quick sort (Lomuto) | II | In-place ordering in the analytics view |
| Binary search | II | Threshold lookup on sorted score arrays |
| Inversion counting | II | Quantifying section reordering |
| LCS (word-level DP) | III | Word-span similarity between documents |
| Edit distance | III | Character-level difference and field drift |
| Tree traversal (BFS/DFS) | I | Walking the document structure tree |
| Huffman coding | IV | Lossless archival of extracted text |
| Bipartite matching (Edmonds–Karp) | V | Field-to-label assignment |
| Set cover (greedy + exhaustive) | VI | Selecting the minimal rule set that explains a verdict |

See `docs/VIT_DAA_SYLLABUS_MAPPING.md` for the full unit-by-unit mapping.

---

## API reference

38 endpoints across ten routers. The full OpenAPI schema is at `/docs`.

| Group | Prefix | Highlights |
| --- | --- | --- |
| Documents | `/api/documents` | Upload, list, detail, text, structure, preview, download, delete |
| Verification | `/api/verify`, `/api/verifications` | Re-run verification, history, run detail with findings |
| Comparison | `/api/compare` | Pairwise similarity, field diff, PDF export |
| Duplicates | `/api/duplicates` | Groups, cluster detail, summary |
| Templates | `/api/templates` | Full CRUD on field/section templates |
| Algorithms | `/api/algorithms` | Catalogue, run, history |
| Benchmarks | `/api/benchmarks` | Run, list, summary, CSV export |
| Reports | `/api/reports` | Generate, fetch, JSON payload, PDF download |
| Analytics | `/api/analytics` | Overview and per-algorithm statistics |
| Settings | `/api/settings` | Get, update, reset |

---

## Why the code is structured this way

- **The pipeline is a DAG, and the DAG is real.** Stage order is computed by a
  topological sort and recorded on every run, so the ordering is auditable
  rather than implied by the sequence of function calls.
- **Three separate statuses.** `validation_status`, `duplicate_status`, and
  `review_recommendation` are independent. A document can be a valid duplicate,
  or an invalid original. Collapsing them into one field loses the reason a
  decision was made.
- **Every decision names its evidence.** Each verification finding carries the
  rule ID, severity, and the measurements behind it.
- **SQLite foreign keys are enforced.** The pipeline flushes parent rows before
  inserting children, so an interrupted ingest cannot leave orphaned rows.
- **Graceful degradation, not silent failure.** Missing Tesseract, an
  unsupported extension, or an unreadable page produces a recorded, explained
  failure rather than an exception or a wrong answer.

---

## Documentation

| Document | Contents |
| --- | --- |
| `docs/BASE_REPOSITORY_AUDIT.md` | Audit of the upstream base repository |
| `docs/UPSTREAM_README.md` | The original repository README, preserved verbatim |
| `docs/FRONTEND_DESIGN_SKILL.md` | The frontend design system and implementation order |
| `docs/VIT_DAA_SYLLABUS_MAPPING.md` | Unit I–VI mapping to VIT Pune syllabus |
| `docs/ALGORITHM_COMPLEXITY.md` | Complexity table with derivations |
| `docs/CORRECTNESS_PROOFS.md` | Correctness arguments per algorithm |
| `docs/RECURRENCE_RELATIONS.md` | Recurrences and their solutions |
| `docs/DYNAMIC_PROGRAMMING.md` | DP formulations and space optimisations |
| `docs/GREEDY_ANALYSIS.md` | Greedy choice properties and counterexamples |
| `docs/NETWORK_FLOW.md` | Flow formulation for matching |
| `docs/NP_COMPLETENESS.md` | Set cover, reductions, approximation bounds |
| `docs/BENCHMARK_RESULTS.md` | Measured performance data |
| `docs/PROJECT_DEMO.md` | End-to-end walkthrough script |

---

## License

Released for academic use as part of a Design and Analysis of Algorithms course
project. Derived from
[SIMILAR-DOCUMENT-TEMPLATE-MATCHING-ALGORITHM](https://github.com/ra-mkum-ar/SIMILAR-DOCUMENT-TEMPLATE-MATCHING-ALGORITHM);
see `docs/BASE_REPOSITORY_AUDIT.md` for what was retained and what was rebuilt.
