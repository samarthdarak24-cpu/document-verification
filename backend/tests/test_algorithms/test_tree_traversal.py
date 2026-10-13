"""Tests for :mod:`app.algorithms.tree_traversal` (tree traversal & validation)."""

import json

import pytest

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


def sample_tree() -> DocumentNode:
    return build_tree({
        "name": "Document",
        "children": [
            {"name": "Header", "children": [
                {"name": "Title"},
                {"name": "Reference Number"},
            ]},
            {"name": "Body", "children": [
                {"name": "Applicant Details"},
            ]},
            {"name": "Footer"},
        ],
    })


DFS_ORDER = ["Document", "Header", "Title", "Reference Number", "Body",
             "Applicant Details", "Footer"]
BFS_ORDER = ["Document", "Header", "Body", "Footer", "Title",
             "Reference Number", "Applicant Details"]


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def test_build_from_nested_dict():
    root = sample_tree()
    assert root.name == "Document"
    assert [c.name for c in root.children] == ["Header", "Body", "Footer"]
    header = root.children[0]
    assert [c.name for c in header.children] == ["Title", "Reference Number"]


def test_build_from_list_creates_synthetic_root():
    root = build_tree([{"name": "A"}, {"name": "B", "children": [{"name": "C"}]}])
    assert root.name == "Document"
    assert [c.name for c in root.children] == ["A", "B"]
    assert root.children[1].children[0].name == "C"


def test_add_child_returns_node_and_sets_parent():
    root = DocumentNode("root")
    child = root.add_child(DocumentNode("c"))
    assert child.parent is root
    assert root.children == [child]


def test_unique_ids():
    root = sample_tree()
    ids = set()
    def collect(n):
        ids.add(n.id)
        for c in n.children:
            collect(c)
    collect(root)
    assert len(ids) == 7


# --------------------------------------------------------------------------- #
# traversals
# --------------------------------------------------------------------------- #
def test_dfs_preorder():
    assert dfs(sample_tree()).order == DFS_ORDER


def test_bfs_level_order():
    assert bfs(sample_tree()).order == BFS_ORDER


def test_traversal_counts():
    d = dfs(sample_tree())
    b = bfs(sample_tree())
    assert d.visited_count == 7 == b.visited_count
    assert d.max_depth == 2 == b.max_depth


def test_single_node():
    root = DocumentNode("solo")
    assert dfs(root).order == ["solo"]
    assert bfs(root).order == ["solo"]
    assert dfs(root).max_depth == 0
    assert dfs(root).visited_count == 1


# --------------------------------------------------------------------------- #
# traces
# --------------------------------------------------------------------------- #
def test_dfs_trace():
    r = dfs(sample_tree(), trace=True)
    for s in r.steps:
        assert set(s.keys()) == {"node", "depth", "action", "stack"}
        assert s["action"] in {"visit", "backtrack"}
    assert any(s["action"] == "visit" for s in r.steps)
    assert any(s["action"] == "backtrack" for s in r.steps)
    # 7 nodes -> at least 7 visit steps
    assert sum(1 for s in r.steps if s["action"] == "visit") == 7


def test_bfs_trace():
    r = bfs(sample_tree(), trace=True)
    for s in r.steps:
        assert set(s.keys()) == {"node", "depth", "action", "queue"}
        assert s["action"] == "visit"
    assert len(r.steps) == 7


def test_trace_empty_by_default():
    assert dfs(sample_tree()).steps == []
    assert bfs(sample_tree()).steps == []


# --------------------------------------------------------------------------- #
# validate_structure
# --------------------------------------------------------------------------- #
def test_validate_present_and_extra():
    root = sample_tree()
    v = validate_structure(root, ["Header/Title", "Body/Applicant Details", "Footer"])
    assert set(v.present) == {"Header/Title", "Body/Applicant Details", "Footer"}
    assert v.missing == []
    assert v.order_ok is True
    assert "Reference Number" in v.extra_sections
    assert any(i["type"] == "unexpected_section" for i in v.issues)


def test_validate_missing():
    root = sample_tree()
    v = validate_structure(root, ["Header/Title", "Signature/Seal"])
    assert "Header/Title" in v.present
    assert "Signature/Seal" in v.missing
    assert v.order_ok is True  # only Header present as top-level -> determinable
    assert any(i["type"] == "missing_section" for i in v.issues)


def test_validate_order_violation():
    root = sample_tree()  # root children order: Header, Body, Footer
    v = validate_structure(root, ["Body/Applicant Details", "Header/Title", "Footer"])
    assert v.order_ok is False
    assert any(i["type"] == "order_violation" for i in v.issues)


def test_validate_plain_name_anywhere():
    root = sample_tree()
    v = validate_structure(root, ["Title", "Applicant Details"])
    assert set(v.present) == {"Title", "Applicant Details"}
    assert v.missing == []


# --------------------------------------------------------------------------- #
# signature & compare
# --------------------------------------------------------------------------- #
def test_signature():
    assert structural_signature(sample_tree()) == (
        "Header/Title; Header/Reference Number; "
        "Body/Applicant Details; Footer"
    )


def test_signature_single_leaf():
    assert structural_signature(build_tree({"name": "Solo"})) == "Solo"


def test_compare_identical():
    cmp = compare_structures(sample_tree(), sample_tree())
    assert cmp["identical"] is True
    assert cmp["only_in_a"] == []
    assert cmp["only_in_b"] == []


def test_compare_diff():
    a = build_tree([{"name": "Header", "children": [{"name": "Title"}]},
                    {"name": "Body", "children": [{"name": "Details"}]}])
    b = build_tree([{"name": "Header", "children": [{"name": "Title"}]},
                    {"name": "Footer", "children": [{"name": "Terms"}]}])
    cmp = compare_structures(a, b)
    assert cmp["identical"] is False
    assert "Header/Title" in cmp["common"]
    assert "Body/Details" in cmp["only_in_a"]
    assert "Footer/Terms" in cmp["only_in_b"]


# --------------------------------------------------------------------------- #
# cycle guard
# --------------------------------------------------------------------------- #
def test_cycle_guard_ancestor():
    root = DocumentNode("root")
    child = root.add_child(DocumentNode("child"))
    gc = child.add_child(DocumentNode("gc"))
    with pytest.raises(ValueError):
        gc.add_child(root)


def test_cycle_guard_self():
    root = DocumentNode("root")
    with pytest.raises(ValueError):
        root.add_child(root)


# --------------------------------------------------------------------------- #
# serialization
# --------------------------------------------------------------------------- #
def test_traversal_to_dict_json():
    r = dfs(sample_tree(), trace=True)
    json.dumps(r.to_dict())
    assert isinstance(r, TraversalResult)


def test_validation_to_dict_json():
    v = validate_structure(sample_tree(), ["Header/Title"])
    json.dumps(v.to_dict())
    assert isinstance(v, StructureValidation)
