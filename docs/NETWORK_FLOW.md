# Network Flow in DocuTrace

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

The last stage of duplicate detection is **field-level corroboration**. Two
documents whose text is 89 % similar might still be genuinely different documents
that share a boilerplate template — or they might be the same document with a
handful of field values changed. Text similarity cannot tell these apart, because
boilerplate is most of the text in both cases.

DocuTrace resolves this by modelling the corroboration as a **maximum bipartite
matching** and solving it with **Edmonds–Karp**. This document gives the flow
formulation, both algorithms, the integrality result that makes the flow answer
*mean* something for a matching, and the concrete place this decides an outcome.

---

## 1. The problem being solved

### 1.1 Why a matching

Given two documents `A` and `B`, extraction yields labelled fields:

```
A: {issuer, registration_no, issue_date, holder_name, programme}
B: {issuer, registration_no, issue_date, holder_name, programme}
```

We want the largest set of field pairs `(a_i, b_j)` such that:

- every `a_i` is used at most once;
- every `b_j` is used at most once;
- a pair may be formed only if the two fields are *compatible* — same canonical
  label and a value match above a per-type threshold.

That is a matching in a bipartite graph: field instances of `A` on the left, field
instances of `B` on the right, an edge for each compatible pair.

|Matching| is the number of fields that can be simultaneously corroborated.
Normalising by the smaller field set gives a **structural corroboration ratio**
that is independent of text length — which is exactly the property text similarity
lacks.

### 1.2 Why not a greedy pairing

The obvious heuristic — walk the fields in order, pair each with its best
compatible partner, mark both used — is the *greedy matching* heuristic. It is not
optimal, and the failure is not exotic.

**Counterexample.** Left fields `a₁, a₂`; right fields `b₁, b₂`. Edges:

```
a₁ — b₁
a₁ — b₂
a₂ — b₁
```

Greedy starts with `a₁`, sees `b₁` and `b₂` both compatible, and in the natural
implementation pairs `a₁–b₁` (first compatible, or highest-scoring). Now `a₂` has
only `b₁`, which is taken, so `a₂` is unmatched.

|Matching| = 1. The optimum is `{a₁–b₂, a₂–b₁}`. **|Matching| = 2.**

The greedy pairing consumed `b₁` — the only neighbour of `a₂` — while `a₁` had an
alternative. This is precisely the situation DocuTrace hits in practice: a
`registration_no` that is compatible with both a `registration_no` and a
`reference_no` on the other side, where the `reference_no` is the only home for
some other field. Greedy gets it wrong; maximum matching does not.

---

## 2. The flow formulation

Bipartite matching reduces to maximum flow on a constructed network
`G' = (V', E')`:

```
        source s
           │  capacity 1
           ▼
   ┌───────────────┐
   │ a₁  a₂  …  aₚ │        left vertices (A's fields)
   └───────────────┘
      │    │    │
      │    │    │            capacity 1 on each compatibility edge
      ▼    ▼    ▼
   ┌───────────────┐
   │ b₁  b₂  …  b_q │        right vertices (B's fields)
   └───────────────┘
           │  capacity 1
           ▼
        sink t
```

Construction rules:

| Edge | Capacity | Purpose |
| --- | --- | --- |
| `s → a_i` | 1 | each left field selected at most once |
| `a_i → b_j` | 1, iff compatible | the compatibility relation |
| `b_j → t` | 1 | each right field selected at most once |

All capacities are integral (all 1). The network has `|V'| = p + q + 2` vertices and
`|E'| = p + q + |E_compat|` edges.

**Theorem NF1 (Max-flow / max-matching).** The value of a maximum `s–t` flow in
`G'` equals the size of a maximum matching in `G`.

*Proof.* (≤) Let `f` be an integral maximum flow. It sends at most 1 unit through
each `a_i → b_j` edge (capacity 1). Define
`M = { (a_i, b_j) : f(a_i → b_j) = 1 }`. Flow conservation at `a_i` and `b_j`,
together with unit capacities on `s → a_i` and `b_j → t`, forces at most one
out-edge at `a_i` and one in-edge at `b_j` to carry flow. So `M` is a matching and
`|M| = value(f)`.

(≥) Let `M` be a matching. Set `f = 1` on `s → a_i` for each saturated `a_i`, on
each matching edge, and on `b_j → t` for each saturated `b_j`; set `f = 0`
elsewhere. Each `a_i` has in-degree 1 and out-flow ≤ 1; each `b_j` has out-degree 1
and in-flow ≤ 1; `s` and `t` balance by construction. So `f` is a feasible flow of
value `|M|`.

The two directions give `max-flow = max-matching`. ∎

---

## 3. Integrality — why the flow answer is the matching answer

The flow reduction is only useful because the maximum flow here is **integral**,
so it corresponds to an actual set of field pairs rather than fractional weights.

**Theorem NF2 (Integrality).** If all capacities are integers, there is a maximum
flow in which every edge carries an integer amount.

*Proof.* Start from the zero flow (integral everywhere). Ford–Fulkerson augments
along a path by the **bottleneck capacity**

```
Δ = min{ c(e) − f(e) : e ∈ P }
```

Each `c(e)` is integral and each `f(e)` is integral by induction, so `c(e) − f(e)`
is a non-negative integer, so `Δ` is a positive integer. Every augmentation adds an
integer to every edge on the path, preserving integrality. The algorithm terminates
(below), and the final flow is integral. ∎

**Consequence.** We never have to round, and "0.7 units of flow through
`a_i → b_j`" cannot occur. The matched-edge set `M = { e : f(e) = 1 }` is a genuine
matching. This is what licenses reading the flow value as a count of corroborated
fields.

**Consequence 2 (why the greedy is not rescued by flow).** Integrality says the
*maximum* flow is a matching. It says nothing about an arbitrary flow: the greedy
pairing of §1.2 corresponds to a flow of value 1 that is not maximum, and
Ford–Fulkerson escapes it by finding an **augmenting path** — for the counterexample,
the path `s → a₂ → b₁ → a₁ → b₂ → t`, which uses the residual back-edge `b₁ → a₁`
to *undo* the greedy choice. That residual back-edge is the whole mechanism: it lets
the algorithm retract a locally reasonable pairing in favour of a globally larger
matching. This is the same idea as the exchange argument in `GREEDY_ANALYSIS.md`,
implemented rather than proved.

---

## 4. Ford–Fulkerson and Edmonds–Karp

### 4.1 Residual network

For a flow `f`, the **residual capacity** of an edge is

```
c_f(u, v) = c(u, v) − f(u, v)          forward direction
c_f(v, u) = f(u, v)                    backward direction (undo capacity)
```

An **augmenting path** is a simple `s–t` path with `c_f(e) > 0` on every edge.
Augmenting along it by `Δ = min_e c_f(e)` yields a larger feasible flow.

**Max-flow min-cut theorem.** A flow is maximum iff no augmenting path exists in
its residual network. (Proved by showing the set of vertices reachable from `s` in
the residual network has no outgoing residual edge, so it forms a cut whose capacity
equals the current flow value; conversely an augmenting path certifies the flow is
not maximum.)

### 4.2 Ford–Fulkerson

```
FordFulkerson(G', s, t):
    f ← zero flow
    while there exists an augmenting path P in residual(G', f):
        Δ ← min { c_f(e) : e ∈ P }
        augment f along P by Δ
    return f
```

Correct (it terminates only at a max flow) but **not polynomial in general**: with
irrational capacities it may not terminate, and even with integer capacities it can
take `O(max-flow)` augmentations. On a graph where the bottleneck is 1 and the max
flow is `F`, that is `F` augmentations regardless of `|V'|`.

### 4.3 Edmonds–Karp: the fix DocuTrace uses

Edmonds–Karp is Ford–Fulkerson with the augmenting path chosen as a **shortest path
by edge count**, found by BFS in the residual network.

```
EdmondsKarp(G', s, t):
    f ← zero flow
    while BFS in residual(G', f) finds a path P from s to t:
        Δ ← min { c_f(e) : e ∈ P }
        augment f along P by Δ
    return f
```

**Why BFS, not DFS.** Choosing the shortest augmenting path makes the **distance
from `s` to every vertex in the residual network non-decreasing** across
augmentations, which bounds the number of augmentations: each augmentation
saturates a *critical* edge, an edge on the shortest path, and the distance
argument shows each edge can be critical at most `O(|V'|)` times. Hence

```
O(|V'| · |E'|) augmentations, each O(|E'|) for the BFS
→  O(|V'| · |E'|²)  total
```

A DFS version has no such bound. That is the entire reason for the BFS.

**On this network** the bound is even friendlier. With unit capacities, all
augmenting paths have bottleneck 1, so Edmonds–Karp performs exactly `|M|` ≤
`min(p, q)` augmentations, each a `Θ(|E'|)` BFS. For DocuTrace's field sets
(`p, q ≤ 16` in the worst realistic case) that is at most 16 BFS passes over a
graph of a few dozen edges — microseconds.

### 4.4 Implementation notes

`app/algorithms/bipartite_matching.py` implements the network explicitly:

- **Vertex numbering.** `source = 0`; left fields `1 … p`; right fields
  `p+1 … p+q`; `sink = p+q+1`. Fixed numbering keeps the trace stable.
- **Residual representation.** Each logical edge owns two `Edge` records
  (forward with capacity 1, backward with capacity 0). Augmenting flips both.
- **Deterministic BFS.** Neighbours are visited in edge-insertion order, so the
  first augmenting path found is unique. This matters because the *set* of matched
  edges can differ between two maximum matchings of the same size, and the
  Laboratory compares traces across runs.
- **Instrumentation.** Each BFS pop, each relaxation, and each augmentation
  appends a `TraceStep`, so the Laboratory can replay the algorithm including the
  residual back-edge that undoes the greedy choice. That replay is the single most
  instructive animation in the DAA Laboratory — a viewer *sees* the algorithm
  retract a decision.
- **Result shape.** Returns `{matching_size, pairs: [(left_label, right_label)],
  ratio}` where `ratio = matching_size / min(p, q)`.

---

## 5. Where this decides an outcome

The six-sample corpus contains the case that motivates the whole mechanism.

**Sample 05 — `05_certificate_reordered.pdf`.** The certificate has the same fields
as the original but reordered and relabelled: `Registration No` appears as
`Reg. No.` and the date is written in a different format. Text-level similarity is
**0.5487** — low, because token order changed and the labels differ. A purely
text-based system would call this *unique* and it would be wrong.

The matching stage recovers it. After canonicalising labels (`Reg. No.` →
`registration_no`) and normalising dates, the compatibility graph has the edges:

```
issuer        ─ issuer
registration  ─ registration
issue_date    ─ issue_date
holder_name   ─ holder_name
```

`|M| = 4` of `min(p,q) = 4`, ratio **1.00**, so the structural evidence says
*every field corroborates*. The verdict is therefore `INCONSISTENT_FIELDS` rather
than `unique`: the values agree field-by-field but the document's *presentation* is
inconsistent, which is exactly the signature of a lightly edited or reissued
document.

Conversely, sample 02 (an exact byte copy) reaches the same `|M| = 4` but via
identical text, so it is resolved far earlier by the SHA-256 stage and never needs
the matching. The matching stage is the backstop for *low-text-similarity* document
pairs, and sample 05 is where it earns its place.

The greedy pairing of §1.2 would also return 4 here — the counterexample is not
present in this particular sample — which is precisely why the *test suite* carries
the counterexample explicitly rather than relying on the corpus. A real corpus
rarely exhibits the adversarial case; the unit test must.

---

## 6. Complexity summary

| Quantity | Value |
| --- | --- |
| Network size | `\|V'\| = p + q + 2`, `\|E'\| = p + q + \|E_compat\|` |
| Augmentations (unit capacities) | exactly `\|M\|` ≤ `min(p, q)` |
| Per augmentation | one BFS, `Θ(\|E'\|)` |
| **Edmonds–Karp total** | **`O(\|V'\| · \|E'\|²)`** general; `O(\|M\| · \|E'\|)` on this network |
| Space | `O(\|V'\| + \|E'\|)` |
| Ford–Fulkerson | `O(F · \|E'\|)` where `F` = max-flow value; not polynomial in the input |
| Greedy matching | `O(\|E'\|)` — **incorrect** (see §1.2) |

Measured cost for the Laboratory's largest instance (`p = q = 100`, dense
compatibility) is **211.5 ms** median, 200.2 ms best, 205.2 ms worst — see
`BENCHMARK_RESULTS.md` §5. That cost is entirely the BFS-per-augmentation bookkeeping
in Python, not the algorithm; the operation count is exactly 100 per run, matching
`min(p, q)`. This is why the matching stage is bounded by configuration and never
runs on full field sets from large corpora in the live pipeline.

---

## 7. Correctness enforcement in code

| Claim | Enforced by |
| --- | --- |
| Flow value equals matching size bound `min(p,q)` | `test_bipartite_matching.py::test_complete_bipartite_is_perfect` |
| Result is a genuine matching (no reused vertex) | `test_bipartite_matching.py::test_result_vertices_are_distinct` |
| Augmenting path undoes the greedy choice | `test_bipartite_matching.py::test_augmenting_path_beats_greedy` |
| Résumé-style instance with empty right side | `test_bipartite_matching.py::test_unbalanced_instance` |
| No augmenting path remains at termination | `test_bipartite_matching.py::test_no_augmenting_path_at_end` |
| Deterministic BFS ordering | `test_bipartite_matching.py::test_deterministic_result` |
| Integrality: flow values are 0/1 | `test_bipartite_matching.py::test_flow_is_integral` |

---

*See also:* `CORRECTNESS_PROOFS.md` §14 (Berge's theorem and the greedy
counterexample), `GREEDY_ANALYSIS.md` §1.2 (the greedy failure this fixes),
`NP_COMPLETENESS.md` (why bipartite matching is *not* hard while set cover is),
`ALGORITHM_COMPLEXITY.md`, `BENCHMARK_RESULTS.md` §5.
