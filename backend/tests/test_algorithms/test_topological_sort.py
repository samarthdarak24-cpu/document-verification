"""Tests for topological_sort (Unit I — Kahn's algorithm, DAGs)."""

import pytest

from app.algorithms.topological_sort import (
    CycleError,
    topological_sort,
    verification_pipeline_dag,
)


def test_empty_graph():
    result = topological_sort([], [])
    assert result.order == []
    assert result.node_count == 0 and result.edge_count == 0


def test_single_node():
    result = topological_sort(["only"], [])
    assert result.order == ["only"]


def test_chain_respects_dependencies():
    result = topological_sort(
        ["upload", "validate", "extract", "report"],
        [("upload", "validate"), ("validate", "extract"), ("extract", "report")],
    )
    order = result.order
    assert order.index("upload") < order.index("validate")
    assert order.index("validate") < order.index("extract")
    assert order.index("extract") < order.index("report")


def test_diamond_dependencies():
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]
    result = topological_sort(nodes, edges)
    order = result.order
    for u, v in edges:
        assert order.index(u) < order.index(v)
    assert result.node_count == 4 and result.edge_count == 4


def test_cycle_detected():
    with pytest.raises(CycleError) as excinfo:
        topological_sort(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "b")])
    assert "cycle" in str(excinfo.value).lower()


def test_self_loop_is_cycle():
    with pytest.raises(CycleError):
        topological_sort(["a"], [("a", "a")])


def test_unknown_node_edge_rejected():
    with pytest.raises(ValueError):
        topological_sort(["a"], [("a", "ghost")])


def test_trace_records_steps():
    result = topological_sort(["a", "b"], [("a", "b")], trace=True)
    assert len(result.steps) == 2
    assert result.steps[0]["removed"] == "a"
    assert set(result.steps[0].keys()) == {"removed", "remaining", "reason"}


def test_verification_pipeline_dag_is_schedulable():
    dag = verification_pipeline_dag()
    result = topological_sort(dag["nodes"], dag["edges"])
    order = result.order
    assert len(order) == len(dag["nodes"])
    for u, v in dag["edges"]:
        assert order.index(u) < order.index(v), f"{u} must precede {v}"
    assert order[0] == "upload"
    assert order[-1] == "report_generation"


def test_pipeline_cycle_detection():
    dag = verification_pipeline_dag()
    # Inject a cycle: report must precede upload (impossible ordering).
    with pytest.raises(CycleError):
        topological_sort(dag["nodes"], dag["edges"] + [("report_generation", "upload")])
