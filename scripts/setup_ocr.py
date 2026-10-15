#!/usr/bin/env python
"""Install and verify the OCR dependency (Tesseract) for DocuTrace.

The Python client (``pytesseract``) is a normal pip dependency and is already
declared in ``backend/requirements.txt``. The Tesseract *binary* is a system
dependency that pip cannot provide, so this script handles it:

  1. Checks whether a Tesseract binary already answers.
  2. If not, downloads the official Windows build from GitHub
     (``UB-Mannheim/tesseract`` — the distribution recommended by the upstream
     ``tesseract-ocr`` project) or tells you the package-manager command for
     your platform.
  3. Points the app at the installed binary via ``TESSERACT_CMD``.

Usage
-----
    python scripts/setup_ocr.py            # check, and install if missing
    python scripts/setup_ocr.py --check    # report only, change nothing
    python scripts/setup_ocr.py --dir DIR  # choose the install directory

Why the binary cannot be installed from inside the app container: the sandbox
in an agent session refuses to launch downloaded installers ("Access is
denied"). Run this script from a normal terminal where you can approve the UAC
prompt, or install it yourself with one of the commands it prints.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

#: The upstream-recommended Windows distribution (GitHub releases).
WINDOWS_INSTALLER = (
    "tesseract-ocr-w64-setup-5.4.0.20240606.exe",
    "https://github.com/UB-Mannheim/tesseract/releases/download/"
    "v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe",
)

#: Where a standard install puts the binary, per platform.
DEFAULT_PATHS = {
    "Windows": [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        Path.home() / r"AppData\Local\Tesseract-OCR\tesseract.exe",
    ],
    "Darwin": ["/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract"],
    "Linux": ["/usr/bin/tesseract", "/usr/local/bin/tesseract"],
}

PLATFORM_COMMANDS = {
    "Windows": [
        "# Option A — winget (installs to Program Files and updates PATH)",
        "winget install --id UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements",
        "",
        "# Option B — the official installer this repo has already downloaded for you",
        f'"{REPO_ROOT / ".ocr-setup" / WINDOWS_INSTALLER[0]}" /VERYSILENT /NORESTART',
    ],
    "Darwin": ["brew install tesseract"],
    "Linux": [
        "# Debian / Ubuntu",
        "sudo apt-get update && sudo apt-get install -y tesseract-ocr",
        "# Fedora",
        "sudo dnf install -y tesseract",
    ],
}

INSTALL_DIR_HINT = {
    "Windows": r"C:\Program Files\Tesseract-OCR",
    "Darwin": "/opt/homebrew",
    "Linux": "/usr/local",
}


def _platform() -> str:
    """Normalise ``sys.platform`` to one of the keys used above."""
    if sys.platform.startswith("win") or sys.platform in {"cygwin", "msys"}:
        return "Windows"
    if sys.platform == "darwin":
        return "Darwin"
    return "Linux"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _tesseract_answers(cmd: str) -> bool:
    """True when ``cmd --version`` succeeds."""
    try:
        proc = _run([cmd, "--version"])
        return proc.returncode == 0 and "tesseract" in (proc.stdout or "").lower()
    except Exception:
        return False


def _find_existing() -> str | None:
    """Return a working tesseract path from PATH or the default install dirs."""
    on_path = shutil.which("tesseract")
    if on_path and _tesseract_answers(on_path):
        return on_path
    for candidate in DEFAULT_PATHS.get(_platform(), []):
        path = str(candidate)
        if Path(path).exists() and _tesseract_answers(path):
            return path
    return None


def _python_client_ready() -> tuple[bool, str]:
    try:
        import pytesseract  # noqa: F401
    except Exception as exc:
        return False, f"pytesseract is not installed ({exc})"
    return True, ""


def _install_python_client() -> bool:
    print("  Installing the Python client: pip install pytesseract")
    proc = _run([sys.executable, "-m", "pip", "install", "pytesseract==0.3.13"])
    return proc.returncode == 0


def _download_installer(destination: Path) -> Path:
    name, url = WINDOWS_INSTALLER
    target = destination / name
    if target.exists() and target.stat().st_size > 1_000_000:
        print(f"  Reusing the already-downloaded {name}")
        return target

    print(f"  Downloading {name} from GitHub ...")
    print(f"    {url}")
    with urllib.request.urlopen(url, timeout=600) as response, open(
        target, "wb"
    ) as handle:
        shutil.copyfileobj(response, handle)
    print(f"    saved {target.stat().st_size / 1e6:.1f} MB to {target}")
    return target


def _write_env_file(tesseract_cmd: str) -> Path:
    """Persist ``TESSERACT_CMD`` for the backend so PATH is irrelevant."""
    env_path = BACKEND / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = [
            line
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("TESSERACT_CMD")
        ]
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"TESSERACT_CMD={tesseract_cmd}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report status only, install nothing"
    )
    parser.add_argument(
        "--dir", default=INSTALL_DIR_HINT.get(_platform()),
        help="directory to install Tesseract into",
    )
    args = parser.parse_args()

    print("DocuTrace — OCR dependency setup")
    print("=" * 68)

    # 1. Python client ------------------------------------------------------ #
    client_ok, client_reason = _python_client_ready()
    print(f"  python client (pytesseract): "
          f"{'present' if client_ok else 'MISSING — ' + client_reason}")
    if not client_ok and not args.check:
        client_ok = _install_python_client()

    # 2. Binary ------------------------------------------------------------- #
    found = _find_existing()
    if found:
        print(f"  tesseract binary           : {found}")
        version = _run([found, "--version"]).stdout.splitlines()[0]
        print(f"  version                    : {version.strip()}")
        # Persist the explicit path so the backend never depends on the shell
        # PATH — a freshly installed binary only reaches *new* shells, so a
        # server launched from an IDE or before the install would otherwise
        # never see it. ``--check`` is documented as report-only, so it skips
        # the write.
        if not args.check and Path(found).is_absolute():
            env_path = _write_env_file(found)
            print(f"  wrote TESSERACT_CMD={found} to {env_path}")
        print("\nOCR is ready — no installation needed.")
        return 0

    print("  tesseract binary           : NOT FOUND")
    print("\n  OCR cannot run without the Tesseract binary (pip cannot install it).")
    print(f"  Install it for {_platform()} with one of:\n")
    for line in PLATFORM_COMMANDS.get(_platform(), PLATFORM_COMMANDS["Linux"]):
        print(f"    {line}")

    if args.check:
        return 1

    if _platform() != "Windows":
        print("\n  Re-run this script after installing with the command above.")
        return 1

    # 3. Windows: fetch the official build, then hand the user the one step - #
    print("\n  Preparing the official Windows installer ...")
    try:
        workdir = Path(tempfile.mkdtemp(prefix="docutrace-ocr-"))
        installer = _download_installer(workdir)
    except Exception as exc:
        print(f"    download failed: {exc}")
        return 1

    default = str(args.dir or INSTALL_DIR_HINT["Windows"])
    print(f"\n  Installer : {installer}")
    print(f"  Run this in an elevated terminal (a UAC prompt will appear):")
    print(f'      "{installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="{default}"')
    print("\n  This script cannot launch the installer itself in a sandboxed")
    print("  session, so please run the command above, then re-run:")
    print("      python scripts/setup_ocr.py --check")

    # Record the intended location so the app finds it without PATH.
    tess = Path(default) / "tesseract.exe"
    if tess.exists():
        env_path = _write_env_file(str(tess))
        print(f"\n  Wrote TESSERACT_CMD={tess} to {env_path}")
    else:
        print(f"\n  After installing, re-run this script: it will write "
              f"TESSERACT_CMD to backend/.env for you.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
