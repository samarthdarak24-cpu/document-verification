"""Optimal verification-rule selection — a weighted set-cover experiment.

Purpose
-------
An OPTIONAL academic experiment (kept strictly separate from the mandatory
verification pipeline). Given verification requirements and candidate rules
with costs and coverage, choose the cheapest collection of rules that covers
every requirement.

Problem form
------------
This is the weighted SET COVER problem:

    minimize    sum_i c_i x_i
    subject to  for every requirement j:  sum_{i: j in covers(i)} x_i >= 1
                x_i in {0, 1}

Set Cover is NP-hard; the decision version ("can all requirements be covered
with cost <= K") is NP-complete — a proposed solution is easy to verify in
polynomial time, but no polynomial-time algorithm is known for solving it in
general. Consequently:

* ``solve_set_cover_exhaustive`` explores all 2^n subsets — exponential.
* ``greedy_set_cover`` is a polynomial-time approximation with an
  O(log n) approximation ratio; it is NOT guaranteed optimal.
* The real DocuTrace pipeline always runs every mandatory check; this
  experiment never influences verification outcomes.

Complexity
----------
* Exhaustive: O(2^n * n * m) — enumerates every subset and re-computes
  coverage; feasible only for tiny instances (n <= ~20 documented limit).
* Greedy: O(T * n * m) where T <= n rounds, each scanning all uncovered
  requirements against all rules.
"""

from __future__ import annotations

import time
from typing import Optional


def greedy_set_cover(
    requirements: list[str],
    rules: list[dict],
    trace: bool = False,
) -> dict:
    """Greedy approximation: repeatedly pick the cheapest uncovered-coverage rule.

    Each rule is ``{"name": str, "cost": float, "covers": list[str]}``. The
    choice rule is *additional requirement coverage per unit cost* with
    deterministic tie-breaking (lower absolute cost, then name).
    """
    start_ns = time.perf_counter_ns()
    uncovered = set(requirements)
    selected: list[str] = []
    total_cost = 0.0
    steps: list[dict] = []

    rule_names = [r["name"] for r in rules]
    if len(set(rule_names)) != len(rule_names):
        raise ValueError("rule names must be unique")

    while uncovered:
        best: Optional[dict] = None
        best_ratio = -1.0
        for rule in rules:
            gain = len(set(rule["covers"]) & uncovered)
            if gain == 0:
                continue
            ratio = gain / rule["cost"] if rule["cost"] > 0 else float("inf")
            candidate_key = (-ratio, rule["cost"], rule["name"])
            best_key = (
                (-best_ratio, best["cost"], best["name"]) if best else None
            )
            if best is None or candidate_key < best_key:
                best, best_ratio = rule, ratio
        if best is None:
            break  # remaining requirements uncovered by any rule
        gain = sorted(set(best["covers"]) & uncovered)
        uncovered -= set(gain)
        selected.append(best["name"])
        total_cost += best["cost"]
        if trace:
            steps.append({
                "selected": best["name"],
                "newly_covered": gain,
                "remaining": sorted(uncovered),
                "cost_so_far": round(total_cost, 4),
            })

    return {
        "strategy": "greedy",
        "selected": selected,
        "total_cost": round(total_cost, 6),
        "covered": sorted(set(requirements) - uncovered),
        "uncovered": sorted(uncovered),
        "complete": len(uncovered) == 0,
        "steps": steps if trace else [],
        "elapsed_ns": time.perf_counter_ns() - start_ns,
    }


def solve_set_cover_exhaustive(
    requirements: list[str],
    rules: list[dict],
    trace: bool = False,
    max_rules: int = 20,
) -> dict:
    """Exhaustive optimum over all subsets of ``rules``.

    Refuses instances with more than ``max_rules`` rules (2^n blowup) unless
    ``max_rules`` is raised explicitly — the caller acknowledges the cost.
    """
    start_ns = time.perf_counter_ns()
    if len(rules) > max_rules:
        raise ValueError(
            f"exhaustive search refused: {len(rules)} rules > max_rules="
            f"{max_rules} (2^n blowup); use greedy_set_cover instead"
        )

    required = set(requirements)
    best_selection: Optional[list[str]] = None
    best_cost = float("inf")
    combinations_examined = 0

    for mask in range(1 << len(rules)):
        combinations_examined += 1
        covered = set()
        cost = 0.0
        selection: list[str] = []
        for i, rule in enumerate(rules):
            if mask & (1 << i):
                covered.update(rule["covers"])
                cost += rule["cost"]
                selection.append(rule["name"])
        if required.issubset(covered) and cost < best_cost:
            best_cost, best_selection = cost, selection

    return {
        "strategy": "exhaustive",
        "selected": best_selection or [],
        "total_cost": round(best_cost, 6) if best_selection else None,
        "covered": sorted(required) if best_selection else [],
        "uncovered": [] if best_selection else sorted(required),
        "complete": best_selection is not None,
        "combinations_examined": combinations_examined,
        "steps": [],
        "elapsed_ns": time.perf_counter_ns() - start_ns,
    }


def compare_selection_strategies(
    requirements: list[str],
    rules: list[dict],
) -> dict:
    """Run both strategies and compare objective value and wall-clock time."""
    greedy = greedy_set_cover(requirements, rules, trace=True)
    exhaustive = solve_set_cover_exhaustive(requirements, rules)
    optimal = exhaustive["total_cost"]
    return {
        "greedy": greedy,
        "exhaustive": exhaustive,
        "greedy_is_optimal": (
            greedy["complete"]
            and optimal is not None
            and abs(greedy["total_cost"] - optimal) < 1e-9
        ),
        "approximation_factor": (
            round(greedy["total_cost"] / optimal, 4)
            if greedy["complete"] and optimal else None
        ),
    }
