"""Huffman coding — greedy construction of optimal prefix-free codes.

Purpose
-------
Demonstrate a greedy algorithm on real data: losslessly compressing extracted
document text for archival. The algorithm repeatedly merges the two
least-frequent symbols, which yields the minimum expected code length among
prefix-free codes for a known symbol distribution.

Greedy choice property
----------------------
Merging the two lowest-frequency nodes first is safe because in an optimal
prefix tree the two least-frequent symbols are siblings at the deepest level
(exchanging any deeper pair with them cannot increase the expected code
length). This exchange argument proves the greedy step optimal.

DocuTrace use case
------------------
Optional archival compression of extracted text in the document store. It is
NOT used to replace PDF storage and it is NOT claimed to always reduce size:
the returned ``total_compressed_bytes`` includes the serialized codebook, and
for tiny or high-entropy texts that overhead can exceed the original size.

Complexity
----------
* Time O(n log n) for n distinct symbols (heap operations dominate).
* Space O(n) for the tree and code table.

Correctness
-----------
The code is prefix-free (every code is a root-to-leaf path), and
``decoded_length == len(text)`` with an exact round trip verifies that the
tree encodes a bijection over the symbol stream.
"""

from __future__ import annotations

import heapq
import itertools
import json
import math
import time
from typing import Optional


class HuffmanResult:
    """Result of a :func:`huffman_encode` call."""

    def __init__(
        self,
        frequency: dict[str, int],
        codes: dict[str, str],
        tree: Optional[dict],
        original_bytes: int,
        payload_bits: int,
        metadata_bytes: int,
        round_trip_ok: bool,
        decoded_length: int,
        elapsed_ns: int,
    ) -> None:
        self.frequency: dict[str, int] = frequency
        self.codes: dict[str, str] = codes
        self.tree: Optional[dict] = tree
        self.original_bytes: int = original_bytes
        self.payload_bits: int = payload_bits
        self.compressed_bytes: int = math.ceil(payload_bits / 8)
        self.metadata_bytes: int = metadata_bytes
        self.total_compressed_bytes: int = self.compressed_bytes + metadata_bytes
        self.compression_ratio: float = (
            self.total_compressed_bytes / original_bytes if original_bytes else 0.0
        )
        self.round_trip_ok: bool = round_trip_ok
        self.decoded_length: int = decoded_length
        self.elapsed_ns: int = elapsed_ns

    def to_dict(self) -> dict:
        return {
            "frequency": dict(self.frequency),
            "codes": dict(self.codes),
            "tree": self.tree,
            "original_bytes": self.original_bytes,
            "payload_bits": self.payload_bits,
            "compressed_bytes": self.compressed_bytes,
            "metadata_bytes": self.metadata_bytes,
            "total_compressed_bytes": self.total_compressed_bytes,
            "compression_ratio": round(self.compression_ratio, 4),
            "round_trip_ok": self.round_trip_ok,
            "decoded_length": self.decoded_length,
            "elapsed_ns": self.elapsed_ns,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"HuffmanResult(symbols={len(self.frequency)}, "
            f"ratio={self.compression_ratio:.3f})"
        )


class _Node:
    __slots__ = ("weight", "order", "symbol", "left", "right")

    def __init__(self, weight: int, order: int, symbol: Optional[str] = None,
                 left: Optional["_Node"] = None, right: Optional["_Node"] = None) -> None:
        self.weight = weight
        self.order = order          # deterministic tie-break
        self.symbol = symbol
        self.left = left
        self.right = right


def _serialize(node: Optional[_Node]) -> Optional[dict]:
    if node is None:
        return None
    if node.symbol is not None:
        return {"symbol": node.symbol, "weight": node.weight, "leaf": True}
    return {
        "leaf": False,
        "weight": node.weight,
        "left": _serialize(node.left),
        "right": _serialize(node.right),
    }


def _decode(bits: str, root: Optional[_Node]) -> Optional[list[str]]:
    if root is None:
        return None if bits else []
    if root.symbol is not None:
        # Single-symbol tree: every bit expands to that symbol.
        return [root.symbol] * len(bits)
    out: list[str] = []
    node = root
    for bit in bits:
        node = node.left if bit == "0" else node.right
        if node is None:
            return None
        if node.symbol is not None:
            out.append(node.symbol)
            node = root
    return out if node is root else None


def huffman_encode(text: str, include_tree_metadata: bool = True) -> HuffmanResult:
    """Build a Huffman code for ``text`` and verify a lossless round trip.

    Empty input yields empty structures. A single distinct symbol gets the
    code ``"0"``. ``include_tree_metadata`` controls whether the serialized
    codebook is counted in ``total_compressed_bytes`` (it always is for the
    round-trip check, but the size accounting can exclude it for display).
    """
    start_ns = time.perf_counter_ns()

    frequency: dict[str, int] = {}
    for ch in text:
        frequency[ch] = frequency.get(ch, 0) + 1

    counter = itertools.count()
    heap: list[tuple[int, int, _Node]] = []
    for symbol, freq in sorted(frequency.items()):
        heapq.heappush(heap, (freq, next(counter), _Node(freq, next(counter), symbol)))

    if not heap:
        return HuffmanResult({}, {}, None, 0, 0, 0, True, 0,
                             time.perf_counter_ns() - start_ns)

    if len(heap) == 1:
        (_, _, only) = heap[0]
        root = only
        codes = {only.symbol: "0"}
    else:
        while len(heap) > 1:
            w1, _, a = heapq.heappop(heap)
            w2, _, b = heapq.heappop(heap)
            merged = _Node(w1 + w2, next(counter), left=a, right=b)
            heapq.heappush(heap, (merged.weight, merged.order, merged))
        root = heap[0][2]

        codes: dict[str, str] = {}

        def _walk(node: _Node, prefix: str) -> None:
            if node.symbol is not None:
                codes[node.symbol] = prefix or "0"
                return
            _walk(node.left, prefix + "0")
            _walk(node.right, prefix + "1")

        _walk(root, "")

    # Encode + verify a lossless round trip.
    payload = "".join(codes[ch] for ch in text)
    decoded = _decode(payload, root)
    round_trip_ok = decoded is not None and "".join(decoded) == text

    original_bytes = len(text.encode("utf-8"))
    metadata_bytes = len(json.dumps(codes, ensure_ascii=False).encode("utf-8")) \
        if include_tree_metadata else 0

    return HuffmanResult(
        frequency=frequency,
        codes=codes,
        tree=_serialize(root),
        original_bytes=original_bytes,
        payload_bits=len(payload),
        metadata_bytes=metadata_bytes,
        round_trip_ok=round_trip_ok,
        decoded_length=len(decoded) if decoded is not None else 0,
        elapsed_ns=time.perf_counter_ns() - start_ns,
    )
