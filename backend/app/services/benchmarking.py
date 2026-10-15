"""Real, measured benchmarks for the DocuTrace algorithm core.

Every number in this module is a **measurement**, not an estimate:

* time comes from ``time.perf_counter_ns`` around the algorithm call;
* memory comes from ``tracemalloc`` peak tracking around the same call;
* operation counts come from the algorithm core's own counters
  (``comparisons``, ``dp_cell_updates``, ``merges``, ...);
* each measurement is repeated ``repeats`` times and reported as the **median**
  (the median resists the scheduler noise that a mean would happily average in).

Dataset generators
------------------
The interesting part of a benchmark is not "how fast is it" but "how does it
behave on its worst input". Each generator therefore targets a specific
complexity case:

===================  =============================================================
``best_case``        Pattern absent / input already sorted / all tokens equal
``typical_case``     Random text over a small alphabet (average behaviour)
``worst_case``       KMP-adversarial repeated characters; reverse-sorted for the
                     comparison sorts (last-element pivot quicksort)
``repeated_character`` A single character repeated (LPS/DP degeneracy)
``random_text``      Uniform random tokens
``similar_text``     Two texts differing in a few tokens (near-duplicate regime)
``different_text``   Two disjoint texts (no shared content)
===================  =============================================================

Sizes are ``[100, 500, 1000, 2500, 5000]``, but the O(n*m) DP algorithms (LCS,
edit distance) are capped at ``[100, 250, 500, 1000]`` so a single cell product
never exceeds the 2,000,000-cell budget: 1000x1000 is already ~10^6 DP cells,
and 2500x2500 would be 6.25 * 10^6 *in pure Python* — a benchmark that takes
minutes teaches nothing and blocks the API.
"""

from __future__ import annotations

import random
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.algorithms.binary_search import binary_search
from app.algorithms.bipartite_matching import bipartite_match, build_matching_problem
from app.algorithms.edit_distance import edit_distance
from app.algorithms.huffman import huffman_encode
from app.algorithms.inversions import count_inversions
from app.algorithms.kmp import kmp_search
from app.algorithms.lcs import lcs_length_optimized
from app.algorithms.merge_sort import merge_sort
from app.algorithms.quick_sort import quick_sort
from app.algorithms.rabin_karp import rabin_karp_search
from app.algorithms.topological_sort import topological_sort, verification_pipeline_dag

#: Sizes used for every algorithm.
SIZES: Tuple[int, ...] = (100, 500, 1000, 2500, 5000)

#: Sizes used for the quadratic-time DP algorithms.
DP_SIZES: Tuple[int, ...] = (100, 250, 500, 1000)

#: Maximum DP cell product for a single benchmark run.
DP_CELL_LIMIT = 2_000_000

#: Default number of timed repetitions per measurement.
DEFAULT_REPEATS = 3

_ALPHABET = "abcde"


# --------------------------------------------------------------------------- #
# Dataset generators
# --------------------------------------------------------------------------- #
def _random_text(n: int, seed: int = 0) -> str:
    """Random text over a small alphabet (deterministic for a given seed)."""
    rng = random.Random(seed)
    return "".join(rng.choice(_ALPHABET) for _ in range(n))


def best_case(n: int) -> str:
    """Sorted/already-matching input: no structural work for pattern search."""
    return "".join(sorted(_random_text(n, seed=1)))


def typical_case(n: int) -> str:
    """Average-case input: random text over a 5-letter alphabet."""
    return _random_text(n, seed=2)


def worst_case(n: int) -> str:
    """Adversarial input for KMP/sort: a single repeated character."""
    return "a" * n


def repeated_character(n: int) -> str:
    """Alias of :func:`worst_case` kept for benchmark granularity."""
    return "a" * n


def random_text(n: int) -> str:
    """Uniformly random tokens (broad alphabet, sparse duplicates)."""
    rng = random.Random(7)
    return " ".join(
        "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6))
        for _ in range(max(1, n // 6))
    )


def similar_text(n: int) -> str:
    """Two near-identical token lists (the near-duplicate regime)."""
    base = random_text(n)
    return base + " extra tail tokens that differ"


def different_text(n: int) -> str:
    """Two token lists with no shared content."""
    return "".join(chr((ord("z") - 1 - (i % 20)) % 26 + 97) for i in range(n))


DATASETS: Dict[str, Callable[[int], str]] = {
    "best_case": best_case,
    "typical_case": typical_case,
    "worst_case": worst_case,
    "repeated_character": repeated_character,
    "random_text": random_text,
    "similar_text": similar_text,
    "different_text": different_text,
}


def dataset_names() -> List[str]:
    """Return the available dataset generator names."""
    return list(DATASETS)


# --------------------------------------------------------------------------- #
# Benchmark driver
# --------------------------------------------------------------------------- #
@dataclass
class BenchmarkRow:
    """One measured benchmark sample."""

    algorithm: str
    input_size: int
    dataset_type: str
    case_type: str
    execution_time_ms: float
    memory_bytes: int
    operations: int
    repeats: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "input_size": self.input_size,
            "dataset_type": self.dataset_type,
            "case_type": self.case_type,
            "execution_time_ms": round(self.execution_time_ms, 4),
            "memory_bytes": self.memory_bytes,
            "operations": self.operations,
            "repeats": self.repeats,
        }


@dataclass
class _Measurement:
    """Median-of-repeats measurement of one callable."""

    times_ms: List[float] = field(default_factory=list)
    peak_bytes: List[int] = field(default_factory=list)
    operations: List[int] = field(default_factory=list)

    def add(self, elapsed_ms: float, peak_bytes: int, operations: int) -> None:
        self.times_ms.append(elapsed_ms)
        self.peak_bytes.append(peak_bytes)
        self.operations.append(operations)

    def row(
        self, algorithm: str, input_size: int, dataset_type: str, case_type: str
    ) -> BenchmarkRow:
        return BenchmarkRow(
            algorithm=algorithm,
            input_size=input_size,
            dataset_type=dataset_type,
            case_type=case_type,
            execution_time_ms=statistics.median(self.times_ms) if self.times_ms else 0.0,
            memory_bytes=int(statistics.median(self.peak_bytes)) if self.peak_bytes else 0,
            operations=(
                int(statistics.median(self.operations)) if self.operations else 0
            ),
            repeats=len(self.times_ms),
        )


def _measure(call: Callable[[], int], repeats: int) -> _Measurement:
    """Time and memory-profile ``call`` ``repeats`` times."""
    measurement = _Measurement()
    for _ in range(max(1, repeats)):
        tracemalloc.start()
        started = time.perf_counter_ns()
        operations = int(call() or 0)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        measurement.add(elapsed_ms, peak, operations)
    return measurement


def _run_one(repeats: int, algorithm: str, input_size: int, dataset_type: str,
            case_type: str, call: Callable[[], int]) -> BenchmarkRow:
    return _measure(call, repeats).row(algorithm, input_size, dataset_type, case_type)


# --------------------------------------------------------------------------- #
# Per-algorithm benchmark bodies
# --------------------------------------------------------------------------- #
def _bench_kmp(text: str, pattern: str) -> int:
    return kmp_search(text, pattern).comparisons


def _bench_rabin_karp(text: str, pattern: str) -> int:
    return rabin_karp_search(text, pattern).hash_comparisons


def _bench_lcs(a: Sequence[str], b: Sequence[str]) -> int:
    length, updates = lcs_length_optimized(list(a), list(b))
    return updates


def _bench_edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    return edit_distance(list(a), list(b)).dp_cell_updates


def _bench_merge_sort(items: List[int]) -> int:
    return merge_sort(items).comparisons


def _bench_quick_sort(items: List[int]) -> int:
    return quick_sort(items).comparisons


def _bench_binary_search(sorted_items: List[int], target: int) -> int:
    return binary_search(sorted_items, target).comparisons


def _bench_inversions(items: List[int]) -> int:
    return count_inversions(items).comparisons


def _bench_huffman(text: str) -> int:
    return sum(huffman_encode(text).frequency.values())


def _bench_topological_sort() -> int:
    dag = verification_pipeline_dag()
    result = topological_sort(dag["nodes"], dag["edges"])
    return len(result.order)


def _bench_bipartite(n: int) -> int:
    left = [f"field_{index}" for index in range(n)]
    right = [f"label_{index}" for index in range(n)]
    problem = build_matching_problem(left, right, similarity_threshold=0.0)
    return bipartite_match(problem).max_matching_size


# --------------------------------------------------------------------------- #
# Suite definition
# --------------------------------------------------------------------------- #
def _token_list(text: str) -> List[str]:
    return [token for token in text.split(" ") if token]


def _dp_size_pairs(size: int) -> Tuple[int, int]:
    """Return ``(size_a, size_b)`` clamped so the cell budget is respected."""
    if size * size <= DP_CELL_LIMIT:
        return size, size
    reduced = int((DP_CELL_LIMIT) ** 0.5)
    return reduced, reduced


def run_algorithm_benchmarks(
    *,
    algorithms: Optional[Sequence[str]] = None,
    datasets: Optional[Sequence[str]] = None,
    sizes: Optional[Sequence[int]] = None,
    repeats: int = DEFAULT_REPEATS,
) -> List[BenchmarkRow]:
    """Run the benchmark suite and return measured rows.

    ``algorithms``/``datasets``/``sizes`` restrict the run; the defaults are the
    full documented suite. No row is ever fabricated: an algorithm that cannot
    run on a dataset (for example, a string algorithm on an empty input) simply
    produces no row.
    """
    selected_algorithms = list(algorithms or _DEFAULT_ALGORITHMS)
    selected_datasets = list(datasets or list(DATASETS))
    selected_sizes = list(sizes or SIZES)
    rows: List[BenchmarkRow] = []

    for dataset_name in selected_datasets:
        generator = DATASETS.get(dataset_name)
        if generator is None:
            continue
        for size in selected_sizes:
            text = generator(size)
            case_type = _case_type_for(dataset_name)
            if "kmp" in selected_algorithms:
                rows.append(
                    _run_one(
                        repeats, "kmp", size, dataset_name, case_type,
                        lambda t=text: _bench_kmp(t, "a" * min(64, max(1, size // 10))),
                    )
                )
            if "rabin_karp" in selected_algorithms:
                rows.append(
                    _run_one(
                        repeats, "rabin_karp", size, dataset_name, case_type,
                        lambda t=text: _bench_rabin_karp(t, "a" * min(64, max(1, size // 10))),
                    )
                )
            if "lcs" in selected_algorithms:
                a_size, b_size = _dp_size_pairs(size)
                if size in DP_SIZES or a_size == size:
                    tokens_a = _token_list(random_text(size))
                    tokens_b = _token_list(similar_text(size))
                    rows.append(
                        _run_one(
                            repeats, "lcs", size, dataset_name, case_type,
                            lambda a=tokens_a, b=tokens_b: _bench_lcs(a, b),
                        )
                    )
            if "edit_distance" in selected_algorithms:
                if size in DP_SIZES:
                    tokens_a = _token_list(random_text(size))
                    tokens_b = _token_list(similar_text(size))
                    rows.append(
                        _run_one(
                            repeats, "edit_distance", size, dataset_name, case_type,
                            lambda a=tokens_a, b=tokens_b: _bench_edit_distance(a, b),
                        )
                    )
            if "merge_sort" in selected_algorithms:
                items = _numeric_items(size, dataset_name)
                rows.append(
                    _run_one(
                        repeats, "merge_sort", size, dataset_name, case_type,
                        lambda xs=items: _bench_merge_sort(xs),
                    )
                )
            if "quick_sort" in selected_algorithms:
                items = _numeric_items(size, dataset_name)
                rows.append(
                    _run_one(
                        repeats, "quick_sort", size, dataset_name, case_type,
                        lambda xs=items: _bench_quick_sort(xs),
                    )
                )
            if "binary_search" in selected_algorithms:
                items = sorted(_numeric_items(size, dataset_name))
                target = items[len(items) // 2] if items else 0
                rows.append(
                    _run_one(
                        repeats, "binary_search", size, dataset_name, case_type,
                        lambda xs=items, t=target: _bench_binary_search(xs, t),
                    )
                )
            if "count_inversions" in selected_algorithms:
                items = _numeric_items(size, dataset_name)
                rows.append(
                    _run_one(
                        repeats, "count_inversions", size, dataset_name, case_type,
                        lambda xs=items: _bench_inversions(xs),
                    )
                )
            if "huffman_encode" in selected_algorithms:
                rows.append(
                    _run_one(
                        repeats, "huffman_encode", size, dataset_name, case_type,
                        lambda t=text: _bench_huffman(t),
                    )
                )
            if "topological_sort" in selected_algorithms and size == SIZES[0]:
                rows.append(
                    _run_one(
                        repeats, "topological_sort", 13, dataset_name, case_type,
                        lambda: _bench_topological_sort(),
                    )
                )
            if "bipartite_match" in selected_algorithms and size <= 100:
                rows.append(
                    _run_one(
                        repeats, "bipartite_match", size, dataset_name, case_type,
                        lambda n=size: _bench_bipartite(n),
                    )
                )
    return rows


#: Algorithms included in the default suite.
_DEFAULT_ALGORITHMS: Tuple[str, ...] = (
    "kmp", "rabin_karp", "lcs", "edit_distance", "merge_sort", "quick_sort",
    "binary_search", "count_inversions", "huffman_encode", "topological_sort",
    "bipartite_match",
)


def algorithm_names() -> List[str]:
    """Return the benchmarkable algorithm names."""
    return list(_DEFAULT_ALGORITHMS)


def _numeric_items(size: int, dataset_name: str) -> List[int]:
    """Build a numeric input list matching the dataset's case type."""
    rng = random.Random(size * 31 + len(dataset_name))
    if dataset_name in {"best_case"}:
        return list(range(size))
    if dataset_name in {"worst_case", "repeated_character"}:
        return list(range(size, 0, -1))  # reverse-sorted: quicksort's worst case
    return [rng.randint(0, size * 10) for _ in range(size)]


def _case_type_for(dataset_name: str) -> str:
    """Map a dataset name to its complexity case classification."""
    if dataset_name in {"best_case"}:
        return "best"
    if dataset_name in {"worst_case", "repeated_character"}:
        return "worst"
    return "average"


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def persist_benchmark_rows(db: Any, rows: Sequence[BenchmarkRow]) -> int:
    """Store measured rows in ``benchmark_results`` and return the count."""
    from app.models.models import BenchmarkResult

    for row in rows:
        db.add(
            BenchmarkResult(
                algorithm=row.algorithm,
                input_size=row.input_size,
                dataset_type=row.dataset_type,
                case_type=row.case_type,
                execution_time_ms=row.execution_time_ms,
                memory_bytes=row.memory_bytes,
                operations=row.operations,
                repeats=row.repeats,
            )
        )
    db.flush()
    return len(rows)


def summarise(rows: Sequence[BenchmarkRow]) -> Dict[str, Any]:
    """Aggregate rows per algorithm (median time, peak memory, growth factor)."""
    grouped: Dict[str, List[BenchmarkRow]] = {}
    for row in rows:
        grouped.setdefault(row.algorithm, []).append(row)

    summary: Dict[str, Any] = {}
    for algorithm, group in grouped.items():
        ordered = sorted(group, key=lambda item: item.input_size)
        growth = None
        if len(ordered) >= 2 and ordered[0].execution_time_ms > 0:
            first, last = ordered[0], ordered[-1]
            if last.input_size > first.input_size:
                size_ratio = last.input_size / first.input_size
                growth = (last.execution_time_ms / first.execution_time_ms) / size_ratio
        summary[algorithm] = {
            "runs": len(group),
            "input_sizes": [row.input_size for row in ordered],
            "median_ms": round(
                statistics.median(row.execution_time_ms for row in group), 4
            ),
            "max_ms": round(max(row.execution_time_ms for row in group), 4),
            "peak_bytes": max(row.memory_bytes for row in group),
            "operations_max": max(row.operations for row in group),
            "time_growth_per_size_factor": round(growth, 3) if growth else None,
        }
    return summary


def run_and_persist(
    db: Any,
    *,
    algorithms: Optional[Sequence[str]] = None,
    datasets: Optional[Sequence[str]] = None,
    sizes: Optional[Sequence[int]] = None,
    repeats: int = DEFAULT_REPEATS,
) -> Dict[str, Any]:
    """Run the suite, persist the rows and return the summary."""
    rows = run_algorithm_benchmarks(
        algorithms=algorithms, datasets=datasets, sizes=sizes, repeats=repeats
    )
    persist_benchmark_rows(db, rows)
    db.commit()
    return {
        "rows": [row.to_dict() for row in rows],
        "stored": len(rows),
        "summary": summarise(rows),
    }


def known_case_types() -> List[str]:
    """Return the case-type labels used in stored rows."""
    return ["best", "average", "worst"]
