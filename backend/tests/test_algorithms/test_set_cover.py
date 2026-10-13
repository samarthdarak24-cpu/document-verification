"""Tests for the set-cover experiment (Unit VI — NP-hardness)."""

import pytest

from app.algorithms.set_cover import (
    compare_selection_strategies,
    greedy_set_cover,
    solve_set_cover_exhaustive,
)


REQUIREMENTS = ["r1", "r2", "r3", "r4"]
RULES = [
    {"name": "A", "cost": 1.0, "covers": ["r1", "r2"]},
    {"name": "B", "cost": 1.0, "covers": ["r2", "r3"]},
    {"name": "C", "cost": 1.5, "covers": ["r4"]},
    {"name": "D", "cost": 2.0, "covers": ["r1", "r2", "r3", "r4"]},
]


def test_greedy_covers_everything():
    result = greedy_set_cover(REQUIREMENTS, RULES)
    assert result["complete"] is True
    assert result["uncovered"] == []
    assert set(result["selected"]) <= {"A", "B", "C", "D"}
    assert result["total_cost"] > 0


def test_greedy_is_not_always_optimal():
    # Optimum is {D} at cost 2.0; greedy picks A, then B, then C -> 3.5.
    comparison = compare_selection_strategies(REQUIREMENTS, RULES)
    assert comparison["exhaustive"]["total_cost"] == 2.0
    assert comparison["exhaustive"]["selected"] == ["D"]
    assert comparison["greedy"]["selected"] == ["A", "B", "C"]
    assert comparison["greedy"]["total_cost"] == 3.5
    assert comparison["greedy_is_optimal"] is False
    assert comparison["approximation_factor"] == 1.75


def test_exhaustive_finds_optimum_on_small_instance():
    result = solve_set_cover_exhaustive(REQUIREMENTS, RULES)
    assert result["selected"] == ["D"]
    assert result["total_cost"] == 2.0
    assert result["combinations_examined"] == 16


def test_infeasible_instance():
    result = greedy_set_cover(["r1", "unreachable"], RULES)
    assert result["complete"] is False
    assert result["uncovered"] == ["unreachable"]


def test_exhaustive_refuses_large_instances():
    many_rules = [
        {"name": f"rule{i}", "cost": 1.0, "covers": [f"r{i}"]} for i in range(25)
    ]
    with pytest.raises(ValueError, match="max_rules"):
        solve_set_cover_exhaustive([f"r{i}" for i in range(25)], many_rules)


def test_duplicate_rule_names_rejected():
    with pytest.raises(ValueError):
        greedy_set_cover(
            ["r1"],
            [
                {"name": "dup", "cost": 1.0, "covers": ["r1"]},
                {"name": "dup", "cost": 1.0, "covers": ["r1"]},
            ],
        )


def test_greedy_deterministic():
    first = greedy_set_cover(REQUIREMENTS, RULES, trace=True)
    second = greedy_set_cover(REQUIREMENTS, RULES, trace=True)
    assert first["selected"] == second["selected"]


def test_zero_cost_rule_preferred():
    rules = [
        {"name": "free", "cost": 0.0, "covers": ["r1", "r2"]},
        {"name": "paid", "cost": 5.0, "covers": ["r1", "r2", "r3"]},
    ]
    result = greedy_set_cover(["r1", "r2", "r3"], rules)
    # The zero-cost rule is picked first (infinite coverage-per-cost ratio),
    # then greediness still covers r3 rather than leaving it uncovered.
    assert result["selected"][0] == "free"
    assert result["complete"] is True
    assert result["total_cost"] == 5.0


def test_trace_steps_structure():
    result = greedy_set_cover(REQUIREMENTS, RULES, trace=True)
    assert len(result["steps"]) >= 1
    assert {"selected", "newly_covered", "remaining", "cost_so_far"} <= set(
        result["steps"][0]
    )
