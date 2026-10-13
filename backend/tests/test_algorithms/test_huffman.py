"""Tests for Huffman coding (Unit IV — greedy algorithm)."""

from app.algorithms.huffman import huffman_encode


def test_empty_text():
    result = huffman_encode("")
    assert result.codes == {}
    assert result.original_bytes == 0
    assert result.round_trip_ok is True
    assert result.tree is None


def test_single_distinct_symbol():
    result = huffman_encode("aaaa")
    assert result.codes == {"a": "0"}
    assert result.payload_bits == 4
    assert result.round_trip_ok is True


def test_round_trip_and_prefix_free():
    text = "the quick brown fox jumps over the lazy dog. " * 3
    result = huffman_encode(text)
    assert result.round_trip_ok is True
    assert result.decoded_length == len(text)
    codes = list(result.codes.values())
    # Prefix-free: no code is a prefix of another.
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            assert not b.startswith(a)
    # Payload size matches sum(freq * code length).
    expected_bits = sum(result.frequency[s] * len(c) for s, c in result.codes.items())
    assert result.payload_bits == expected_bits


def test_classic_example_total_bits():
    # Textbook frequencies: a5 b9 c12 d13 e16 f45 -> optimal 224 bits.
    freq = {"a": 5, "b": 9, "c": 12, "d": 13, "e": 16, "f": 45}
    text = "".join(s * n for s, n in freq.items())
    result = huffman_encode(text)
    assert result.round_trip_ok is True
    assert result.payload_bits == 224


def test_more_frequent_symbols_get_shorter_codes():
    # a=7, b=2, c=1 -> a gets a 1-bit code, b and c get 2-bit codes.
    text = "aaaaaaabbc"
    result = huffman_encode(text)
    assert result.round_trip_ok is True
    assert len(result.codes["a"]) < len(result.codes["b"])
    assert len(result.codes["a"]) < len(result.codes["c"])


def test_size_accounting_includes_metadata():
    text = "mississippi river"
    with_meta = huffman_encode(text, include_tree_metadata=True)
    without_meta = huffman_encode(text, include_tree_metadata=False)
    assert with_meta.total_compressed_bytes > without_meta.total_compressed_bytes
    assert with_meta.total_compressed_bytes == (
        with_meta.compressed_bytes + with_meta.metadata_bytes
    )
    assert 0.0 <= with_meta.compression_ratio


def test_unicode_text():
    text = "文档验证 文档验证 café café résumé"
    result = huffman_encode(text)
    assert result.round_trip_ok is True
    assert result.decoded_length == len(text)


def test_deterministic_tie_breaking():
    a = huffman_encode("abcd")
    b = huffman_encode("abcd")
    assert a.codes == b.codes
