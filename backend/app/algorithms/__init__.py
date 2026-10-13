"""DocuTrace algorithm core — standalone, testable DAA implementations.

Every module in this package implements its algorithm from scratch (no
third-party similarity libraries), exposes real operation counters and optional
visualization traces, and documents its complexity in the module docstring.

Modules
-------
``kmp``            Knuth-Morris-Pratt exact pattern search (LPS table).
``rabin_karp``     Rolling-hash pattern search with collision verification.
``hashing``        Streaming SHA-256 file/text hashing (cryptographic primitive).
``lcs``            Longest Common Subsequence DP (full + memory-optimized).
``edit_distance``  Levenshtein edit distance DP (full + memory-optimized).
``tree_traversal`` Document tree with BFS/DFS and structural validation.
``merge_sort``     Stable comparison sort (divide & conquer).
``quick_sort``     Last-element-pivot quick sort (divide & conquer).
``binary_search``  Binary search over sorted sequences with pointer trace.
``topological_sort`` Kahn's algorithm over the verification pipeline DAG.
``inversions``     Inversion counting via modified merge sort (D&C).
``huffman``        Huffman coding (greedy prefix codes) for text archival.
``bipartite_matching`` Maximum bipartite matching via Edmonds-Karp max flow.
``set_cover``      Greedy + exhaustive rule-selection (set cover experiment).
"""

from app.algorithms.kmp import KMPResult, build_lps, kmp_search
from app.algorithms.rabin_karp import RabinKarpResult, rabin_karp_search
from app.algorithms.hashing import compute_file_hash_with_stats, sha256_bytes, sha256_file, sha256_text
from app.algorithms.lcs import LCSResult, lcs_dp, lcs_length_optimized, lcs_similarity, tokenize
from app.algorithms.edit_distance import EditDistanceResult, edit_distance, edit_distance_optimized, edit_distance_sequences
from app.algorithms.tree_traversal import (
    DocumentNode,
    StructureValidation,
    TraversalResult,
    bfs,
    build_tree,
    compare_structures,
    dfs,
    structural_signature,
    validate_structure,
)
from app.algorithms.merge_sort import SortResult, merge_sort
from app.algorithms.quick_sort import quick_sort
from app.algorithms.binary_search import BinarySearchResult, binary_search
from app.algorithms.topological_sort import (
    CycleError,
    TopologicalSortResult,
    topological_sort,
    verification_pipeline_dag,
)
from app.algorithms.inversions import InversionResult, count_inversions
from app.algorithms.huffman import HuffmanResult, huffman_encode
from app.algorithms.bipartite_matching import (
    BipartiteGraph,
    bipartite_match,
    build_matching_problem,
)
from app.algorithms.set_cover import greedy_set_cover, solve_set_cover_exhaustive

__all__ = [
    # KMP
    "build_lps", "kmp_search", "KMPResult",
    # Rabin-Karp
    "rabin_karp_search", "RabinKarpResult",
    # SHA-256
    "sha256_bytes", "sha256_text", "sha256_file", "compute_file_hash_with_stats",
    # LCS
    "lcs_dp", "lcs_length_optimized", "lcs_similarity", "tokenize", "LCSResult",
    # Edit distance
    "edit_distance", "edit_distance_optimized", "edit_distance_sequences", "EditDistanceResult",
    # Tree traversal / structure
    "DocumentNode", "build_tree", "dfs", "bfs", "TraversalResult",
    "validate_structure", "StructureValidation", "structural_signature", "compare_structures",
    # Sorting & searching
    "merge_sort", "quick_sort", "SortResult", "binary_search", "BinarySearchResult",
    # Unit I — graphs
    "topological_sort", "TopologicalSortResult", "CycleError", "verification_pipeline_dag",
    # Unit II — divide & conquer
    "count_inversions", "InversionResult",
    # Unit IV — greedy
    "huffman_encode", "HuffmanResult",
    # Unit V — network flow
    "bipartite_match", "BipartiteGraph", "build_matching_problem",
    # Unit VI — NP-hardness experiment
    "greedy_set_cover", "solve_set_cover_exhaustive",
]
