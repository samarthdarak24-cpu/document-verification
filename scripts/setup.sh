#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DocuTrace - one-shot developer setup.
#
# Creates the backend virtualenv, installs Python and Node dependencies, applies
# the database migration, and generates the six sample certificate PDFs.
#
# Usage (from the repository root):
#     bash scripts/setup.sh
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> DocuTrace setup"
echo "    root: $ROOT"
echo

# --------------------------------------------------------------------------- #
# Preconditions
# --------------------------------------------------------------------------- #
command -v python >/dev/null 2>&1 || { echo "[error] python is not on PATH." >&2; exit 1; }
command -v node   >/dev/null 2>&1 || { echo "[error] node is not on PATH." >&2; exit 1; }

echo "    python: $(python --version 2>&1)"
echo "    node:   $(node --version)"
echo

# --------------------------------------------------------------------------- #
# Backend
# --------------------------------------------------------------------------- #
echo "==> Backend: creating virtualenv"
cd "$ROOT/backend"

if [[ ! -d .venv ]]; then
  python -m venv .venv
  echo "    created backend/.venv"
else
  echo "    backend/.venv already exists"
fi

# Resolve the venv's python and pip for both POSIX and Windows layouts.
if [[ -x .venv/bin/python ]]; then
  VENV_PY=".venv/bin/python"
elif [[ -x .venv/Scripts/python.exe ]]; then
  VENV_PY=".venv/Scripts/python.exe"
else
  echo "[error] Could not find the virtualenv interpreter." >&2
  exit 1
fi

echo "==> Backend: installing dependencies"
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -r requirements.txt --quiet
echo "    installed"

echo "==> Backend: applying database migration"
"$VENV_PY" -m alembic upgrade head
echo "    database ready"

# --------------------------------------------------------------------------- #
# Frontend
# --------------------------------------------------------------------------- #
echo
echo "==> Frontend: installing dependencies"
cd "$ROOT/frontend"
npm install --no-audit --no-fund
echo "    installed"

# --------------------------------------------------------------------------- #
# Sample documents
# --------------------------------------------------------------------------- #
echo
echo "==> Generating sample documents"
cd "$ROOT"
"$VENV_PY" scripts/create_sample_documents.py --outdir samples

# --------------------------------------------------------------------------- #
# Smoke test
# --------------------------------------------------------------------------- #
echo
echo "==> Running the test suite"
cd "$ROOT/backend"
"$VENV_PY" -m pytest -q

cd "$ROOT"
echo
echo "==> Setup complete."
echo
echo "Start both servers with:"
echo "    bash scripts/start-all.sh"
echo
echo "Then open http://127.0.0.1:5173"
echo
echo "Note: Tesseract OCR is optional. Without it, scanned PDFs and images are"
echo "reported as unreadable instead of being OCR'd. Native PDFs and DOCX work"
echo "fully without it."
