"""Tests for bipartite matching via Edmonds-Karp (Unit V — network flow)."""

import random

from app.algorithms.bipartite_matching import (
    bipartite_match,
    build_matching_problem,
)


def _reference_max_matching(adjacency, left, right):
    """Textbook recursive Kuhn's algorithm (trusted reference)."""
    match_right = {r: None for r in right}

    def try_kuhn(u, visited):
        for v in adjacency.get(u, []):
            if v in visited:
                continue
            visited.add(v)
            if match_right[v] is None or try_kuhn(match_right[v], visited):
                match_right[v] = u
                return True
        return False

    size = 0
    for u in left:
        if try_kuhn(u, set()):
            size += 1
    return size


def test_perfect_matching_with_aliases():
    expected = [
        {"name": "Student Name", "data_type": "text"},
        {"name": "Roll Number", "data_type": "id"},
        {"name": "Date of Issue", "data_type": "date"},
    ]
    extracted = [
        {"label": "Candidate Name", "data_type": "text"},
        {"label": "Registration Number", "data_type": "id"},
        {"label": "Issued On", "data_type": "date"},
    ]
    aliases = {
        "Student Name": {"Candidate Name"},
        "Roll Number": {"Registration Number"},
        "Date of Issue": {"Issued On"},
    }
    problem = build_matching_problem(expected, extracted, aliases=aliases)
    result = bipartite_match(problem)
    assert result.max_matching_size == 3
    assert result.unmatched_expected == []
    assert result.unmatched_extracted == []
    rules = {e["rule"] for e in problem["edges"]}
    assert "alias" in rules


def test_exact_normalized_labels_match():
    problem = build_matching_problem(
        [{"name": "Invoice Number"}, {"name": "Total Amount"}],
        [{"label": "invoice  number"}, {"label": "TOTAL-AMOUNT"}],
    )
    result = bipartite_match(problem)
    assert result.max_matching_size == 2
    assert {e["rule"] for e in problem["edges"]} == {"exact_label"}


def test_no_edges_when_incompatible():
    problem = build_matching_problem(
        [{"name": "Invoice Number", "data_type": "id"}],
        [{"label": "Completely Unrelated Word", "data_type": "text"}],
    )
    result = bipartite_match(problem)
    assert result.max_matching_size == 0
    assert result.unmatched_expected == ["Invoice Number"]
    assert result.unmatched_extracted == ["Completely Unrelated Word"]


def test_one_extracted_field_cannot_be_claimed_twice():
    # Both expected fields are compatible with the single extracted field.
    problem = build_matching_problem(
        [{"name": "Amount"}, {"name": "Total Amount"}],
        [{"label": "Amount"}],
    )
    result = bipartite_match(problem)
    assert result.max_matching_size == 1
    assert len(result.unmatched_expected) == 1
    matched_pairs = {(l, r) for l, r in result.matching}
    assert all(r == "Amount" for _, r in matched_pairs)


def test_type_incompatibility_blocks_edge():
    problem = build_matching_problem(
        [{"name": "Amount", "data_type": "amount"}],
        [{"label": "amount", "data_type": "date"}],
    )
    assert problem["edges"] == []


def test_randomized_against_reference_kuhn():
    rng = random.Random(99)
    for _ in range(40):
        left = [f"L{i}" for i in range(rng.randint(0, 6))]
        right = [f"R{i}" for i in range(rng.randint(0, 6))]
        edges = [
            (u, v)
            for u in left
            for v in right
            if rng.random() < 0.45
        ]
        problem = {
            "expected": left,
            "extracted": right,
            "edges": [
                {"expected": u, "extracted": v, "similarity": 1.0, "rule": "test"}
                for u, v in edges
            ],
        }
        adjacency: dict[str, list[str]] = {}
        for u, v in edges:
            adjacency.setdefault(u, []).append(v)
        reference_size = _reference_max_matching(adjacency, left, right)
        result = bipartite_match(problem)
        assert result.max_matching_size == reference_size
        assert result.max_flow == reference_size
        # Matching must be a valid partial injection.
        lefts = [l for l, _ in result.matching]
        rights = [r for _, r in result.matching]
        assert len(set(lefts)) == len(lefts)
        assert len(set(rights)) == len(rights)


def test_augmenting_path_trace():
    expected = [{"name": f"Field {i}"} for i in range(3)]
    extracted = [{"label": f"Field {i}"} for i in range(3)]
    problem = build_matching_problem(expected, extracted)
    result = bipartite_match(problem)
    assert result.max_matching_size == 3
    assert len(result.augmenting_paths) >= 1
    assert {"start", "path", "assignments", "displaced"} <= set(
        result.augmenting_paths[0]
    )


def test_determinism():
    problem = build_matching_problem(
        [{"name": "A"}, {"name": "B"}],
        [{"label": "B"}, {"label": "A"}],
    )
    first = bipartite_match(problem).to_dict()
    second = bipartite_match(problem).to_dict()
    first.pop("elapsed_ns"), second.pop("elapsed_ns")
    assert first == second
