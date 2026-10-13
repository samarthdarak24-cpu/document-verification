"""Tests for :mod:`app.algorithms.hashing` (SHA-256 content hashing)."""

from app.algorithms.hashing import (
    compute_file_hash_with_stats,
    sha256_bytes,
    sha256_file,
    sha256_text,
)

# Well-known SHA-256("abc").
ABC_DIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_known_digest_text():
    assert sha256_text("abc") == ABC_DIGEST


def test_known_digest_bytes():
    assert sha256_bytes(b"abc") == ABC_DIGEST


def test_text_and_bytes_agree():
    assert sha256_text("hello") == sha256_bytes("hello".encode("utf-8"))


def test_text_encoding_arg():
    assert sha256_text("é", encoding="utf-8") == sha256_bytes("é".encode("utf-8"))
    # UTF-16 encoding produces a different byte sequence -> different digest.
    assert sha256_text("é", encoding="utf-16") != sha256_text("é", encoding="utf-8")


def test_different_text_different_hash():
    assert sha256_text("abc") != sha256_text("abd")


def test_empty_digest():
    expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_bytes(b"") == expected
    assert sha256_text("") == expected


def test_file_streaming_equals_bytes(tmp_path):
    content = b"The quick brown fox jumps over the lazy dog.\n" * 500
    p = tmp_path / "doc.bin"
    p.write_bytes(content)
    assert sha256_file(str(p)) == sha256_bytes(content)


def test_compute_file_hash_with_stats_fields(tmp_path):
    content = b"X" * (64 * 1024 + 10)  # just over one 64 KiB chunk
    p = tmp_path / "stats.bin"
    p.write_bytes(content)
    stats = compute_file_hash_with_stats(str(p))
    assert set(stats.keys()) == {"sha256", "bytes_read", "chunks"}
    assert stats["bytes_read"] == len(content)
    assert stats["chunks"] >= 2  # spans more than the default 64 KiB chunk
    assert stats["sha256"] == sha256_bytes(content)


def test_stats_small_chunk_size(tmp_path):
    content = b"abcdefghij"  # 10 bytes
    p = tmp_path / "small.bin"
    p.write_bytes(content)
    stats = compute_file_hash_with_stats(str(p), chunk_size=3)
    # 10 bytes / 3 -> chunks of 3,3,3,1 => 4 chunks.
    assert stats["chunks"] == 4
    assert stats["bytes_read"] == 10
    assert stats["sha256"] == sha256_bytes(content)


def test_empty_file_stats(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    stats = compute_file_hash_with_stats(str(p))
    assert stats["bytes_read"] == 0
    assert stats["chunks"] == 0
    assert stats["sha256"] == sha256_bytes(b"")


def test_large_1mb_input():
    import os
    data = os.urandom(1024 * 1024)  # 1 MiB
    digest = sha256_bytes(data)
    assert len(digest) == 64
    # Digest is stable across repeated calls.
    assert sha256_bytes(data) == digest


def test_large_1mb_file_streaming(tmp_path):
    import os
    data = os.urandom(1024 * 1024)
    p = tmp_path / "big.bin"
    p.write_bytes(data)
    assert sha256_file(str(p), chunk_size=65536) == sha256_bytes(data)
