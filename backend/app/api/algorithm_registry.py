"""Interactive algorithm registry for the Algorithm Laboratory (``/api/algorithms``).

Every entry here executes the REAL implementation from ``app.algorithms`` on
caller-supplied input and returns actual measurements plus (where supported) a
step-by-step trace. Nothing is simulated or pre-computed.

The registry also carries the academic metadata the UI displays: the VIT DAA
unit, time/space complexity, and the DocuTrace feature each algorithm powers.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

from app.algorithms import (
    bfs,
    binary_search,
    bipartite_match,
    build_matching_problem,
    build_tree,
    count_inversions,
    dfs,
    edit_distance,
    greedy_set_cover,
    huffman_encode,
    kmp_search,
    lcs_dp,
    merge_sort,
    quick_sort,
    rabin_karp_search,
    sha256_text,
    solve_set_cover_exhaustive,
    structural_signature,
    topological_sort,
    validate_structure,
    verification_pipeline_dag,
)
from app.algorithms.tree_traversal import compare_structures  # noqa: F401 (re-exported for routers)

MAX_TEXT = 200_000
MAX_TOKENS = 3_000


class AlgorithmError(ValueError):
    """Invalid input for an algorithm demonstration."""


def _text(value: Any, name: str, limit: int = MAX_TEXT) -> str:
    if value is None:
        raise AlgorithmError(f"'{name}' is required.")
    if not isinstance(value, str):
        raise AlgorithmError(f"'{name}' must be a string.")
    if len(value) > limit:
        raise AlgorithmError(f"'{name}' is limited to {limit:,} characters.")
    return value


def _int(value: Any, name: str, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise AlgorithmError(f"'{name}' must be an integer.") from None
    if not low <= parsed <= high:
        raise AlgorithmError(f"'{name}' must be between {low} and {high}.")
    return parsed


def _seq(value: Any, name: str) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value][:MAX_TOKENS]
    raise AlgorithmError(f"'{name}' must be a list.")


# --------------------------------------------------------------------------- #
# Input normalisers: each returns the argument list for the real algorithm.
# --------------------------------------------------------------------------- #
def _in_kmp(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "text": _text(inputs.get("text", ""), "text"),
        "pattern": _text(inputs.get("pattern", ""), "pattern", 10_000),
        "trace": bool(inputs.get("trace", True)),
    }


def _in_rabin_karp(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "text": _text(inputs.get("text", ""), "text"),
        "pattern": _text(inputs.get("pattern", ""), "pattern", 10_000),
        "trace": bool(inputs.get("trace", True)),
    }


def _in_sha256(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {"text": _text(inputs.get("text", ""), "text")}


def _in_lcs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    source = inputs.get("source_text", inputs.get("a", ""))
    target = inputs.get("target_text", inputs.get("b", ""))
    return {
        "a": _text(source, "source_text"),
        "b": _text(target, "target_text"),
    }


def _in_edit_distance(inputs: Dict[str, Any]) -> Dict[str, Any]:
    source = inputs.get("source_text", inputs.get("a", ""))
    target = inputs.get("target_text", inputs.get("b", ""))
    return {
        "a": _text(source, "source_text"),
        "b": _text(target, "target_text"),
        "with_operations": bool(inputs.get("with_operations", True)),
    }


def _in_tree(inputs: Dict[str, Any]) -> Dict[str, Any]:
    spec = inputs.get("tree") or inputs.get("spec")
    if not isinstance(spec, (dict, list)):
        raise AlgorithmError("'tree' must be an object or list of section objects.")
    return {
        "spec": spec,
        "required": _seq(inputs.get("required_sections", []) or [], "required_sections"),
        "trace": bool(inputs.get("trace", True)),
    }


def _in_topological(inputs: Dict[str, Any]) -> Dict[str, Any]:
    nodes = inputs.get("nodes")
    edges = inputs.get("edges")
    if nodes in (None, "") or edges in (None, ""):
        dag = verification_pipeline_dag()
        return {"nodes": dag["nodes"], "edges": [tuple(e) for e in dag["edges"]],
                "trace": bool(inputs.get("trace", True))}
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise AlgorithmError("'nodes' and 'edges' must be lists.")
    parsed_edges = []
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            parsed_edges.append((str(edge[0]), str(edge[1])))
        elif isinstance(edge, dict) and "from" in edge and "to" in edge:
            parsed_edges.append((str(edge["from"]), str(edge["to"])))
        else:
            raise AlgorithmError("each edge must be [from, to].")
    return {
        "nodes": [str(n) for n in nodes],
        "edges": parsed_edges,
        "trace": bool(inputs.get("trace", True)),
    }


def _in_inversions(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items") or inputs.get("sequence")
    if items is None:
        raise AlgorithmError("'items' is required (a list of comparable numbers).")
    if not isinstance(items, list):
        raise AlgorithmError("'items' must be a list.")
    try:
        parsed = [float(i) if isinstance(i, (int, float)) else str(i) for i in items]
    except (TypeError, ValueError):  # pragma: no cover - defensive
        raise AlgorithmError("'items' must contain numbers or strings.") from None
    return {"items": parsed[:MAX_TOKENS], "trace": bool(inputs.get("trace", True))}


def _in_sort(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items") or inputs.get("sequence")
    if items is None or not isinstance(items, list):
        raise AlgorithmError("'items' must be a non-empty list.")
    return {"items": items[:MAX_TOKENS], "trace": bool(inputs.get("trace", True))}


def _coerce_target(items: list, target: Any) -> Any:
    """Coerce ``target`` so it is comparable with the elements of ``items``.

    The UI sends every text parameter as a string, but binary search compares
    the target against the elements directly. Without this, searching a numeric
    list for the string ``"7"`` raises ``TypeError: '<' not supported between
    instances of 'int' and 'str'`` (a 500). We align the target with the element
    type instead of rejecting the request, so both ``"7"`` and ``7`` work.
    """
    if isinstance(target, str):
        sample = next((i for i in items if i is not None), None)
        if isinstance(sample, (int, float)) and not isinstance(sample, bool):
            stripped = target.strip()
            try:
                return int(stripped)
            except ValueError:
                try:
                    as_float = float(stripped)
                except ValueError:
                    # Not numeric: fall back to a string comparison on both
                    # sides so the algorithm stays total instead of raising.
                    return target
                return int(as_float) if as_float.is_integer() else as_float
    elif isinstance(target, (int, float)) and not isinstance(target, bool):
        sample = next((i for i in items if i is not None), None)
        if isinstance(sample, str):
            return str(target)
    return target


def _in_binary_search(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items") or inputs.get("sorted_items")
    if not isinstance(items, list) or not items:
        raise AlgorithmError("'items' must be a non-empty sorted list.")
    if "target" not in inputs:
        raise AlgorithmError("'target' is required.")
    trimmed = items[:MAX_TOKENS]
    target = _coerce_target(trimmed, inputs["target"])

    # A binary search is only correct on sorted data; mixed types cannot be
    # ordered at all, so fail loudly rather than returning a wrong answer.
    try:
        ordered = all(trimmed[i] <= trimmed[i + 1] for i in range(len(trimmed) - 1))
    except TypeError:
        raise AlgorithmError(
            "'items' must be orderable (all numbers or all strings) — "
            f"got {sorted({type(i).__name__ for i in trimmed})}."
        ) from None
    if not ordered:
        raise AlgorithmError("'items' must be sorted in ascending order.")

    return {
        "items": trimmed,
        "target": target,
        "trace": bool(inputs.get("trace", True)),
    }


def _in_huffman(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "text": _text(inputs.get("text", ""), "text"),
        "include_tree_metadata": bool(inputs.get("include_tree_metadata", True)),
    }


def _in_bipartite(inputs: Dict[str, Any]) -> Dict[str, Any]:
    expected = inputs.get("expected_fields")
    extracted = inputs.get("extracted_fields")
    if not isinstance(expected, list) or not isinstance(extracted, list):
        raise AlgorithmError("'expected_fields' and 'extracted_fields' must be lists.")
    aliases = inputs.get("aliases") or None
    if aliases is not None and not isinstance(aliases, dict):
        raise AlgorithmError("'aliases' must be an object mapping names to lists.")
    normalized_aliases = None
    if aliases:
        normalized_aliases = {
            str(key): {str(v) for v in values} if isinstance(values, list) else {str(values)}
            for key, values in aliases.items()
        }
    return {
        "expected": expected[:200],
        "extracted": extracted[:200],
        "threshold": float(inputs.get("similarity_threshold", 0.6)),
        "aliases": normalized_aliases,
        "required": _seq(inputs.get("required_sections", []) or [], "required_sections"),
    }


def _in_set_cover(inputs: Dict[str, Any]) -> Dict[str, Any]:
    requirements = inputs.get("requirements")
    rules = inputs.get("rules")
    if not isinstance(requirements, list) or not isinstance(rules, list):
        raise AlgorithmError("'requirements' and 'rules' must be lists.")
    parsed_rules = []
    for rule in rules:
        if not isinstance(rule, dict) or "name" not in rule:
            raise AlgorithmError("each rule must be an object with a 'name'.")
        parsed_rules.append({
            "name": str(rule["name"]),
            "cost": float(rule.get("cost", 1.0)),
            "covers": [str(c) for c in rule.get("covers", [])],
        })
    return {
        "requirements": [str(r) for r in requirements],
        "rules": parsed_rules,
        "include_exhaustive": bool(inputs.get("include_exhaustive", True)),
    }


# --------------------------------------------------------------------------- #
# Runners: each returns (summary_dict, operations, trace)
# --------------------------------------------------------------------------- #
def _run_kmp(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = kmp_search(args["text"], args["pattern"], trace=args["trace"])
    summary = {
        "matches": result.matches,
        "match_count": len(result.matches),
        "comparisons": result.comparisons,
        "pattern_length": len(args["pattern"]),
        "text_length": len(args["text"]),
    }
    return summary, result.comparisons, result.trace


def _run_rabin_karp(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = rabin_karp_search(args["text"], args["pattern"], trace=args["trace"])
    summary = {
        "matches": result.matches,
        "match_count": len(result.matches),
        "hash_comparisons": result.hash_comparisons,
        "char_comparisons": result.char_comparisons,
        "collisions": result.collisions,
        "base": result.base,
        "modulus": result.modulus,
    }
    return summary, result.hash_comparisons, result.trace


def _run_sha256(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    digest = sha256_text(args["text"])
    return {
        "sha256": digest,
        "input_length": len(args["text"]),
        "digest_length": len(digest),
    }, 1, []


def _run_lcs(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = lcs_dp(args["a"], args["b"])
    summary = {
        "length": result.length,
        "similarity": round(result.similarity, 4),
        "matched_tokens": result.matched_tokens[:100],
        "unmatched_source": result.unmatched_a[:100],
        "unmatched_target": result.unmatched_b[:100],
        "dp_cell_updates": result.dp_cell_updates,
        "matrix_available": result.matrix is not None,
        "matrix": result.matrix,
        "alignment": result.alignment[:200],
    }
    return summary, result.dp_cell_updates, []


def _run_edit_distance(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = edit_distance(args["a"], args["b"], with_operations=args["with_operations"])
    summary = {
        "distance": result.distance,
        "similarity": round(result.similarity, 4),
        "operations": result.operations[:100],
        "operation_count": len(result.operations),
        "dp_cell_updates": result.dp_cell_updates,
        "matrix": result.matrix,
    }
    return summary, result.dp_cell_updates, []


def _run_tree(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    root = build_tree(args["spec"])
    depth_result = dfs(root, trace=args["trace"])
    breadth_result = bfs(root, trace=args["trace"])
    validation = validate_structure(root, args["required"]) if args["required"] else None
    summary = {
        "signature": structural_signature(root),
        "dfs_order": depth_result.order,
        "bfs_order": breadth_result.order,
        "dfs_steps": depth_result.steps,
        "bfs_steps": breadth_result.steps,
        "visited_count": depth_result.visited_count,
        "max_depth": depth_result.max_depth,
        "required_sections": args["required"],
        "validation": validation.to_dict() if validation is not None else None,
        "uncertain": False,
    }
    return summary, depth_result.visited_count + breadth_result.visited_count, depth_result.steps


def _run_topological(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    try:
        result = topological_sort(args["nodes"], args["edges"], trace=args["trace"])
    except Exception as exc:  # CycleError is a ValueError subclass
        raise AlgorithmError(str(exc)) from None
    summary = {
        "order": result.order,
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "steps": result.steps,
    }
    return summary, result.node_count + result.edge_count, result.steps


def _run_inversions(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = count_inversions(args["items"], trace=args["trace"])
    summary = {
        "inversion_count": result.inversion_count,
        "n": result.n,
        "comparisons": result.comparisons,
        "normalized_reorder_score": round(result.normalized_reorder_score, 6),
        "trace": result.trace,
    }
    return summary, result.comparisons, result.trace


def _run_merge_sort(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = merge_sort(args["items"], trace=args["trace"])
    summary = {
        "sorted": result.sorted_items[:500],
        "comparisons": result.comparisons,
        "merges": result.merges,
        "input_size": len(args["items"]),
        "trace": result.trace,
    }
    return summary, result.comparisons, result.trace


def _run_quick_sort(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = quick_sort(args["items"], trace=args["trace"])
    summary = {
        "sorted": result.sorted_items[:500],
        "comparisons": result.comparisons,
        "swaps": result.swaps,
        "partitions": result.partitions,
        "pivot_strategy": result.pivot_strategy,
        "input_size": len(args["items"]),
        "trace": result.trace,
    }
    return summary, result.comparisons, result.trace


def _run_binary_search(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = binary_search(args["items"], args["target"], trace=args["trace"])
    summary = {
        "index": result.index,
        "found": result.index >= 0,
        "comparisons": result.comparisons,
        "steps": result.steps,
        "input_size": len(args["items"]),
    }
    return summary, result.comparisons, result.steps


def _run_huffman(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    result = huffman_encode(args["text"], include_tree_metadata=args["include_tree_metadata"])
    summary = {
        "distinct_symbols": len(result.frequency),
        "codes": dict(sorted(result.codes.items(), key=lambda kv: (len(kv[1]), kv[0]))[:60]),
        "tree": result.tree,
        "original_bytes": result.original_bytes,
        "payload_bits": result.payload_bits,
        "compressed_bytes": result.compressed_bytes,
        "metadata_bytes": result.metadata_bytes,
        "total_compressed_bytes": result.total_compressed_bytes,
        "compression_ratio": round(result.compression_ratio, 4),
        "round_trip_ok": result.round_trip_ok,
        "decoded_length": result.decoded_length,
    }
    return summary, len(result.frequency), []


def _run_bipartite(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    problem = build_matching_problem(
        args["expected"], args["extracted"],
        similarity_threshold=args["threshold"], aliases=args["aliases"],
    )
    result = bipartite_match(problem)
    summary = {
        "edges": problem["edges"][:200],
        "edge_count": len(problem["edges"]),
        "matching": [list(pair) for pair in result.matching],
        "matched_expected": result.matched_expected,
        "matched_extracted": result.matched_extracted,
        "unmatched_expected": result.unmatched_expected,
        "unmatched_extracted": result.unmatched_extracted,
        "max_matching_size": result.max_matching_size,
        "max_flow": result.max_flow,
        "augmenting_paths": result.augmenting_paths,
    }
    return summary, len(problem["edges"]) + result.max_matching_size, result.augmenting_paths


def _run_set_cover(args: Dict[str, Any]) -> tuple[Dict[str, Any], int, List[dict]]:
    greedy = greedy_set_cover(args["requirements"], args["rules"], trace=True)
    summary: Dict[str, Any] = {"greedy": greedy, "exhaustive": None,
                               "greedy_is_optimal": None, "approximation_factor": None}
    operations = len(args["requirements"]) * len(args["rules"])
    if args["include_exhaustive"] and len(args["rules"]) <= 20:
        exhaustive = solve_set_cover_exhaustive(args["requirements"], args["rules"])
        summary["exhaustive"] = exhaustive
        operations += exhaustive.get("combinations_examined", 0)
        if exhaustive["total_cost"] is not None:
            summary["greedy_is_optimal"] = (
                greedy["complete"]
                and abs(greedy["total_cost"] - exhaustive["total_cost"]) < 1e-9
            )
            summary["approximation_factor"] = (
                round(greedy["total_cost"] / exhaustive["total_cost"], 4)
                if exhaustive["total_cost"] else None
            )
    return summary, operations, greedy.get("steps", [])


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
RegistryEntry = Dict[str, Any]

REGISTRY: Dict[str, RegistryEntry] = {
    "kmp": {
        "title": "Knuth–Morris–Pratt (KMP)",
        "unit": "String Algorithms (Unit III support)",
        "complexity_time": "O(n + m)",
        "complexity_space": "O(m)",
        "description": (
            "Exact pattern search using a precomputed longest-prefix-suffix table so the "
            "text index never moves backwards. DocuTrace uses KMP to locate required field "
            "labels inside extracted document text."
        ),
        "parameters": [
            {"name": "text", "type": "text", "label": "Document text", "required": True},
            {"name": "pattern", "type": "text", "label": "Pattern / field label", "required": True},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_kmp, "run": _run_kmp,
    },
    "rabin_karp": {
        "title": "Rabin–Karp (rolling hash)",
        "unit": "String Algorithms (Unit III support)",
        "complexity_time": "O(n + m) expected, O(nm) worst",
        "complexity_space": "O(1) auxiliary",
        "description": (
            "Search using a polynomial rolling hash so each window's hash updates in O(1). "
            "Every hash match is re-verified character by character, so collisions can never "
            "produce a false positive."
        ),
        "parameters": [
            {"name": "text", "type": "text", "label": "Document text", "required": True},
            {"name": "pattern", "type": "text", "label": "Pattern", "required": True},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_rabin_karp, "run": _run_rabin_karp,
    },
    "sha256": {
        "title": "SHA-256 file hashing",
        "unit": "Hashing (Unit I analysis)",
        "complexity_time": "O(n)",
        "complexity_space": "O(1) beyond the digest",
        "description": (
            "Cryptographic digest used for byte-identical duplicate detection. A separate "
            "normalized-text hash detects documents whose content is identical after "
            "normalization."
        ),
        "parameters": [
            {"name": "text", "type": "text", "label": "Text to hash", "required": True},
        ],
        "normalise": _in_sha256, "run": _run_sha256,
    },
    "lcs": {
        "title": "Longest Common Subsequence",
        "unit": "Unit III — Dynamic Programming",
        "complexity_time": "O(nm)",
        "complexity_space": "O(nm) full alignment, O(min(n,m)) length-only",
        "description": (
            "Dynamic-programming comparison of token sequences used to measure how much "
            "content two document versions share, with full alignment reconstruction."
        ),
        "parameters": [
            {"name": "source_text", "type": "text", "label": "Original text", "required": True},
            {"name": "target_text", "type": "text", "label": "Modified text", "required": True},
        ],
        "normalise": _in_lcs, "run": _run_lcs,
    },
    "edit_distance": {
        "title": "Levenshtein Edit Distance",
        "unit": "Unit III — Dynamic Programming",
        "complexity_time": "O(nm)",
        "complexity_space": "O(nm) with operations, O(min(n,m)) distance-only",
        "description": (
            "Minimum number of insertions, deletions and substitutions needed to transform "
            "one string into another, with the optimal edit script reconstructed. Used for "
            "field-level change detection."
        ),
        "parameters": [
            {"name": "source_text", "type": "text", "label": "Original value", "required": True},
            {"name": "target_text", "type": "text", "label": "Modified value", "required": True},
            {"name": "with_operations", "type": "boolean", "label": "Reconstruct edit script", "default": True},
        ],
        "normalise": _in_edit_distance, "run": _run_edit_distance,
    },
    "tree_traversal": {
        "title": "Tree Traversal (DFS / BFS)",
        "unit": "Unit I — Graph Traversal",
        "complexity_time": "O(V + E)",
        "complexity_space": "O(V) worst case (stack / queue)",
        "description": (
            "Depth-first and breadth-first traversal of the document section hierarchy, "
            "plus required-section validation. BFS discovers missing sections level by "
            "level; DFS inspects nesting and detects invalid structure."
        ),
        "parameters": [
            {"name": "tree", "type": "json", "label": "Document section tree", "required": True},
            {"name": "required_sections", "type": "json", "label": "Required sections", "default": []},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_tree, "run": _run_tree,
    },
    "topological_sort": {
        "title": "Topological Sort (Kahn's algorithm)",
        "unit": "Unit I — Graphs",
        "complexity_time": "O(V + E)",
        "complexity_space": "O(V + E)",
        "description": (
            "Orders the verification pipeline stages so every dependency runs first, and "
            "detects dependency cycles. Leave nodes/edges empty to use the real DocuTrace "
            "pipeline DAG."
        ),
        "parameters": [
            {"name": "nodes", "type": "json", "label": "Nodes (empty = pipeline DAG)", "default": []},
            {"name": "edges", "type": "json", "label": "Edges [[from, to], ...]", "default": []},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_topological, "run": _run_topological,
    },
    "inversions": {
        "title": "Inversion Counting (modified merge sort)",
        "unit": "Unit II — Divide & Conquer",
        "complexity_time": "O(n log n)",
        "complexity_space": "O(n)",
        "description": (
            "Counts how many pairs of reliably matched document sections are out of order, "
            "quantifying how much a section reordering changed the document."
        ),
        "parameters": [
            {"name": "items", "type": "json", "label": "Section rank sequence", "required": True},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_inversions, "run": _run_inversions,
    },
    "merge_sort": {
        "title": "Merge Sort",
        "unit": "Unit II — Divide & Conquer",
        "complexity_time": "Θ(n log n)",
        "complexity_space": "O(n) auxiliary",
        "description": (
            "Stable divide-and-conquer sort used to rank similarity candidates by score. "
            "T(n) = 2T(n/2) + Θ(n) ⇒ Θ(n log n) by the Master Theorem (case 2)."
        ),
        "parameters": [
            {"name": "items", "type": "json", "label": "Items to sort", "required": True},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_sort, "run": _run_merge_sort,
    },
    "quick_sort": {
        "title": "Quick Sort (last-element pivot)",
        "unit": "Unit II — Divide & Conquer",
        "complexity_time": "Θ(n log n) expected, O(n²) worst",
        "complexity_space": "O(log n) expected recursion depth",
        "description": (
            "In-place partitioning sort with an explicit stack. Expected Θ(n log n); "
            "already-sorted input with a last-element pivot degrades to O(n²), which the "
            "benchmark dashboard demonstrates."
        ),
        "parameters": [
            {"name": "items", "type": "json", "label": "Items to sort", "required": True},
            {"name": "trace", "type": "boolean", "label": "Record step trace", "default": True},
        ],
        "normalise": _in_sort, "run": _run_quick_sort,
    },
    "binary_search": {
        "title": "Binary Search",
        "unit": "Unit II — Searching",
        "complexity_time": "O(log n)",
        "complexity_space": "O(1)",
        "description": (
            "Searches sorted document metadata, exposing the low/mid/high pointers so the "
            "halving process can be stepped through."
        ),
        "parameters": [
            {"name": "items", "type": "json", "label": "Sorted items", "required": True},
            {"name": "target", "type": "text", "label": "Target value", "required": True},
            {"name": "trace", "type": "boolean", "label": "Record pointer trace", "default": True},
        ],
        "normalise": _in_binary_search, "run": _run_binary_search,
    },
    "huffman": {
        "title": "Huffman Coding",
        "unit": "Unit IV — Greedy Algorithms",
        "complexity_time": "O(n log n) for n distinct symbols",
        "complexity_space": "O(n)",
        "description": (
            "Greedy construction of an optimal prefix-free code by repeatedly merging the "
            "two least-frequent symbols. Used to demonstrate lossless compression of "
            "extracted text for archival, with honest size accounting that includes the "
            "codebook."
        ),
        "parameters": [
            {"name": "text", "type": "text", "label": "Text to encode", "required": True},
            {"name": "include_tree_metadata", "type": "boolean", "label": "Count codebook in size", "default": True},
        ],
        "normalise": _in_huffman, "run": _run_huffman,
    },
    "bipartite_matching": {
        "title": "Maximum Bipartite Matching (Edmonds–Karp)",
        "unit": "Unit V — Network Flow",
        "complexity_time": "O(V·E²) — here O(L·R·(L+R))",
        "complexity_space": "O(V + E)",
        "description": (
            "Aligns expected template fields with extracted document fields via a "
            "max-flow reduction, so a single extracted field can never satisfy two "
            "expected fields. Compatible edges come from label normalization, approved "
            "aliases and label similarity."
        ),
        "parameters": [
            {"name": "expected_fields", "type": "json", "label": "Expected template fields", "required": True},
            {"name": "extracted_fields", "type": "json", "label": "Extracted document fields", "required": True},
            {"name": "aliases", "type": "json", "label": "Approved aliases", "default": {}},
            {"name": "similarity_threshold", "type": "number", "label": "Label similarity threshold", "default": 0.6},
        ],
        "normalise": _in_bipartite, "run": _run_bipartite,
    },
    "set_cover": {
        "title": "Verification Rule Selection (Set Cover)",
        "unit": "Unit VI — NP-Completeness",
        "complexity_time": "Greedy O(T·n·m), exhaustive O(2ⁿ·n·m)",
        "complexity_space": "O(n + m)",
        "description": (
            "OPTIONAL academic experiment: choosing the cheapest set of verification rules "
            "that covers every requirement is weighted Set Cover, which is NP-hard. Compares "
            "a polynomial greedy approximation against the exhaustive optimum on small "
            "instances. It never affects real verification outcomes."
        ),
        "parameters": [
            {"name": "requirements", "type": "json", "label": "Verification requirements", "required": True},
            {"name": "rules", "type": "json", "label": "Candidate rules [{name, cost, covers}]", "required": True},
            {"name": "include_exhaustive", "type": "boolean", "label": "Also run exhaustive (≤20 rules)", "default": True},
        ],
        "normalise": _in_set_cover, "run": _run_set_cover,
    },
}


def list_algorithms() -> List[Dict[str, Any]]:
    """Return UI metadata for every registered algorithm (no execution)."""
    return [
        {
            "name": name,
            "title": entry["title"],
            "unit": entry["unit"],
            "complexity_time": entry["complexity_time"],
            "complexity_space": entry["complexity_space"],
            "description": entry["description"],
            "parameters": entry["parameters"],
        }
        for name, entry in REGISTRY.items()
    ]


def run_algorithm(algorithm: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Execute ``algorithm`` on ``inputs`` and return a measured payload.

    Any ``TypeError`` raised inside an algorithm is converted into an
    :class:`AlgorithmError` so a bad input yields a 400 with a useful message
    instead of an opaque 500.
    """
    entry = REGISTRY.get(algorithm)
    if entry is None:
        raise AlgorithmError(
            f"Unknown algorithm '{algorithm}'. Available: {', '.join(REGISTRY)}."
        )
    args = entry["normalise"](inputs)
    started = time.perf_counter()
    try:
        summary, operations, trace = entry["run"](args)
    except AlgorithmError:
        raise
    except TypeError as exc:
        raise AlgorithmError(
            f"Invalid input for '{algorithm}': {exc}"
        ) from None
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "algorithm": algorithm,
        "title": entry["title"],
        "unit": entry["unit"],
        "complexity_time": entry["complexity_time"],
        "complexity_space": entry["complexity_space"],
        "result": summary,
        "operations": int(operations),
        "trace": trace,
        "execution_time_ms": round(elapsed_ms, 4),
    }


__all__ = [
    "AlgorithmError",
    "list_algorithms",
    "run_algorithm",
    "REGISTRY",
    "compare_structures",
    "Callable",
]
