"""SHA-256 content hashing for document fingerprinting.

Purpose
-------
Provide fast, collision-resistant fingerprints of document content so DocuTrace
can (a) de-duplicate uploads at ingest time and (b) do a cheap exact-equality
pre-check before running the (more expensive) similarity algorithms on a pair of
documents.

Why not reimplement SHA-256 here?
---------------------------------
SHA-256 is a cryptographic primitive; reimplementing it in pure Python would be
slow, error-prone, and offer no educational upside for a DAA algorithms package.
This module therefore wraps the standard library's :mod:`hashlib`, whose
SHA-256 implementation is a well-tested FIPS 180-4 construction. Importing it is
the constant-time, always-correct way to get a digest.

Streaming behaviour
-------------------
Files are hashed by streaming fixed-size chunks (default 64 KiB) through
``hashlib.sha256().update(...)`` rather than loading the whole file into memory.

* ``sha256_file`` / ``compute_file_hash_with_stats``:
  - Time O(n) where n = file size in bytes (each byte is read once and fed to
    the hash exactly once).
  - Space O(chunk_size): only one chunk is resident at a time, so arbitrarily
    large PDFs can be hashed in bounded memory.

Database-backed lookup
----------------------
In the wider DocuTrace system a file's SHA-256 is stored in an indexed DB column.
An equality lookup of a digest against that index runs in O(1) expected time
(hash-table B-tree index probe), turning duplicate detection into a constant-time
membership query rather than a linear scan of prior uploads.

Unicode-safe: text is encoded explicitly (UTF-8 by default) before hashing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

_DEFAULT_CHUNK = 65536  # 64 KiB


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data`` (bytes)."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str, encoding: str = "utf-8") -> str:
    """Return the SHA-256 hex digest of ``text`` encoded with ``encoding``."""
    return hashlib.sha256(text.encode(encoding)).hexdigest()


def sha256_file(path: Union[str, Path], chunk_size: int = _DEFAULT_CHUNK) -> str:
    """Stream-hash the file at ``path`` in ``chunk_size`` byte chunks.

    Time O(file size), space O(chunk_size). See module docstring.
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_file_hash_with_stats(
    path: Union[str, Path], chunk_size: int = _DEFAULT_CHUNK
) -> dict:
    """Hash ``path`` while streaming, returning digest plus I/O statistics.

    Returns a dict ``{"sha256": str, "bytes_read": int, "chunks": int}`` where
    ``bytes_read`` is the total number of bytes fed to the hasher and ``chunks``
    is the number of read operations performed. The digest equals
    :func:`sha256_bytes` applied to the file's full contents.
    """
    hasher = hashlib.sha256()
    bytes_read = 0
    chunks = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            bytes_read += len(chunk)
            chunks += 1
    return {"sha256": hasher.hexdigest(), "bytes_read": bytes_read, "chunks": chunks}
