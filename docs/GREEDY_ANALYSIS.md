# Greedy Algorithms in DocuTrace

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

Two algorithms in DocuTrace are greedy: **Huffman coding** and the **greedy
set-cover** used for validation-rule minimisation. They are an instructive pair,
because one is optimal and the other is only an approximation — and the reason is
exactly the presence or absence of the *greedy-choice property*.

This document derives both, proves what can be proved about each, exhibits the
counterexample that separates them, and pins the two approximation bounds to the
actual code in `app/algorithms/`.

---

## 1. The greedy paradigm and what it requires

A greedy algorithm builds a solution one decision at a time, committing
irrevocably to the locally best choice at each step. It is the cheapest paradigm
to implement and the easiest to get wrong.

Greedy is correct when two conditions hold.

**Greedy-choice property.** There exists an optimal solution that contains the
greedy choice. Proving this usually takes an *exchange argument*: take any optimal
solution, show the greedy choice can replace part of it without making it worse,
and conclude that some optimal solution starts with the greedy choice.

**Optimal substructure.** After committing the greedy choice, the remaining
problem is a subproblem of the same kind, so induction applies.

| Algorithm | Greedy-choice property | Optimal substructure | Outcome |
| --- | --- | --- | --- |
| Huffman coding | Yes — Lemma G1 (exchange) | Yes | **Optimal** |
| Greedy set cover | **No** | Yes | **H(U)-approximation, not optimal** |

That table is the whole story. Everything below is the work of establishing each
cell.

---

## 2. Huffman coding

### 2.1 Where it runs

DocuTrace compresses the normalised token stream of very large documents before
storing the intermediate representation in `algorithm_runs` — the raw token
sequence of a 500-page PDF is several megabytes, and the SQLite blob store is
happier with hundreds of kilobytes. Huffman is chosen over a fixed 8-bit encoding
because the token-frequency distribution is strongly skewed: in a certificate
corpus, `the`, `of`, `and`, digits and date fragments dominate, while most tokens
occur once or twice. A code that gives the common tokens short codewords pays for
itself immediately.

This is the one place in DocuTrace where an algorithm is chosen purely for
constant-factor performance on data we already have, rather than to answer a
question. It is included in the DAA catalogue because it is the canonical
correct-greedy algorithm and because its proof is a clean exchange argument.

### 2.2 The algorithm

Given symbols with frequencies `f: Σ → ℕ⁺`:

```
Huffman(S, f):
    Q ← min-heap of leaves, keyed by f, one per symbol in S
    while |Q| > 1:
        x ← ExtractMin(Q)          # least frequent
        y ← ExtractMin(Q)          # second least frequent
        z ← new internal node with children x, y and freq f[x] + f[y]
        Insert(Q, z)
    return ExtractMin(Q)           # the root
```

Each merge removes two trees and creates one, so exactly `n − 1` merges occur and
the result is a full binary tree with `n` leaves. The codeword for a symbol is the
root-to-leaf path, with `0` for a left edge and `1` for a right edge.

**No codeword is a prefix of another.** Every symbol is a leaf and every codeword
is the unique root-to-leaf path, so one codeword cannot be an initial segment of
another — such a segment would have to end at an internal node, and codewords end
only at leaves. This is the **prefix-free property**, and it is what makes
decoding unambiguous without separators.

### 2.3 Implementation notes

DocuTrace's implementation in `app/algorithms/huffman.py` uses the algorithm's own
minimum heap rather than importing `heapq`, so that the `operations` counter and
the step `trace` are complete:

```python
heap = Heap()                       # binary min-heap, instrumented
for symbol, freq in frequencies.items():
    heap.push(Node(symbol, freq))

while heap.size() > 1:
    left = heap.pop()
    right = heap.pop()
    merged = Node(None, left.freq + right.freq, left=left, right=right)
    heap.push(merged)
    trace.append(TraceStep(...))    # records the merge
root = heap.pop()
```

Every comparison inside the heap passes through a counter, so the `operations`
number in `algorithm_runs` is the true key-comparison count, not an estimate. That
is what makes the measured growth in `BENCHMARK_RESULTS.md` meaningful.

### 2.4 Why greedy is optimal here: the exchange argument

**Lemma G1 (exchange).** Let `x` and `y` be the two symbols of lowest frequency in
`Σ`. Then there is an optimal prefix-free code in which `x` and `y` are siblings
at maximum depth.

*Proof.* Take any optimal tree `T`. Let `a` and `b` be two siblings of maximum
depth, with `d(a) = d(b) = h` maximal and `f(a) ≤ f(b)`. We show we can exchange
`a ↔ x` without increasing cost.

Since `f(x)` is minimal, `f(x) ≤ f(a)`. Consider swapping `x` and `a` in `T`.
The cost change is

```
Δ = f(x)·h + f(a)·d(x) − f(x)·d(x) − f(a)·h
  = (f(a) − f(x)) · (d(x) − h)
```

Since `f(a) ≥ f(x)` and `h ≥ d(x)` (because `h` is the maximum depth), both
factors are non-negative, so `Δ ≥ 0` — the cost did not increase when we moved the
cheaper symbol `x` to the deeper position. Symmetrically, swapping `y` into `b`'s
position does not increase cost either, using `f(y) ≤ f(b)`.

After both swaps, `x` and `y` occupy positions of maximum depth. If they are not
siblings, their parents are two internal nodes at depth `h − 1`, and exchanging the
subtrees to make `x` and `y` siblings is cost-neutral (both are at the same depth
`h`, so reattaching leaves at the same depth changes nothing). The result is an
optimal tree in which `x` and `y` are siblings at maximum depth. ∎

**Theorem G1 (Huffman optimality).** The Huffman tree is an optimal prefix-free
code.

*Proof (induction on n = |Σ|).*

*Base.* `n = 2`. Both symbols get depth 1, cost `f(x) + f(y)`. Any prefix-free code
must assign distinct codewords; the minimum total depth budget for two leaves is
2, achieved only at depth 1 each. Optimal.

*Inductive step.* Let `x`, `y` be the lowest-frequency symbols, and form the
reduced alphabet `Σ' = Σ − {x,y} ∪ {z}` with `f(z) = f(x) + f(y)`. By Lemma G1,
some optimal tree `T` for `Σ` has `x`, `y` as siblings at maximum depth.

Removing the common parent turns `T` into a prefix-free tree `T'` for `Σ'`.
Crucially,

```
cost(T) = cost(T') + f(x) + f(y)
```

because the sibling pair at depth `h` contributes `(f(x) + f(y))·h` in `T`, and in
`T'` the merged node sits at depth `h − 1`, contributing `(f(x)+f(y))·(h−1)`; the
difference is exactly `f(x) + f(y)`.

By the induction hypothesis, the Huffman tree for `Σ'` is optimal, so
`cost(Huffman(Σ')) ≤ cost(T')`. The Huffman recursion for `Σ` produces exactly
`Huffman(Σ')` with the leaf `z` expanded into the sibling pair `x, y`. Therefore

```
cost(Huffman(Σ)) = cost(Huffman(Σ')) + f(x) + f(y)
                 ≤ cost(T') + f(x) + f(y)
                 = cost(T)
```

and since `T` was optimal, `cost(Huffman(Σ)) = cost(T)`. ∎

**The greedy-choice property is Lemma G1; the optimal substructure is the
reduction `Σ → Σ'`.** Both cells of the table are now filled.

### 2.5 The optimality certificate: Kraft equality

A binary prefix-free code satisfies the **Kraft inequality**

```
Σ_{c ∈ C} 2^(−|c|) ≤ 1
```

and the Huffman tree — being a *full* binary tree with `n` leaves — satisfies it
with equality:

```
Σ_{c ∈ C} 2^(−|c|) = 1
```

DocuTrace asserts this in `test_huffman.py` for every generated tree. It is a cheap,
strong check: a code that is prefix-free but not full (some internal node has one
child) would satisfy the inequality strictly, and that is never optimal because
collapsing the unary node shortens every codeword below it. The equality assertion
therefore catches a class of bugs (unary nodes left in the tree) that a
prefix-freeness test alone would miss.

### 2.6 Complexity

| Step | Cost |
| --- | --- |
| Build frequency table | `Θ(n)` |
| Build initial heap | `Θ(n)` build-heap |
| `n − 1` × (two pops + one push) | `O(n log n)` |
| Walk tree for codewords | `Θ(n)` |
| **Total** | **`Θ(n log n)`** |

where `n` is the number of *distinct* symbols. The measured operations column
confirms the shape: 100 / 500 / 1000 / 2500 / 5000 symbols cost 100 / 500 / 1000 /
2500 / 5000 median operations respectively — the median run sees each symbol
exactly once beyond the heap, and the max column (141 / 610 / 1191 / 2941 / 5860)
shows the `n log n` heap traffic becoming visible under the average case. See
`BENCHMARK_RESULTS.md` §4.

### 2.7 Recurrence

The telescoping from Theorem G1 gives the cost recurrence

```
T(n) = T(n − 1) + Θ(log n)
```

since each merge reduces the heap by one and the two heap operations cost
`O(log n)`. Unrolling:

```
T(n) = Σ_{k=2}^{n} Θ(log k) = Θ(log(n!)) = Θ(n log n)     (Stirling)
```

`RECURRENCE_RELATIONS.md` §8 solves this in full.

---

## 3. Set cover — the greedy that is *not* optimal

### 3.1 Where it runs

DocuTrace's validation engine has eight rules (R001–R008). For a small document
class, running all eight costs more than it returns: several rules are subsumed by
others, and a few are irrelevant to the given template. The engine therefore
selects a **minimum-cost subset of rules** that covers every *validation obligation*
the document class defines.

Formally:

- **Universe `U`** = the set of obligations to be discharged (e.g. "issuer identity
  is present", "issue date is parseable", "date ordering is consistent").
- **Rules `R`** = candidate rules, each covering a subset `S_r ⊆ U` and carrying a
  cost `c(r)` proportional to its measured execution time.
- **Goal** = choose `R' ⊆ R` minimising `Σ_{r ∈ R'} c(r)` such that
  `⋃_{r ∈ R'} S_r = U`.

Minimum set cover is NP-hard (`NP_COMPLETENESS.md` §3 reduces Vertex Cover to it).
DocuTrace therefore runs **two** solvers and reports both:

1. a **greedy `H(U)`-approximation**, used in the live pipeline because it is fast;
2. an **exhaustive optimum**, used in the DAA Laboratory for small instances so the
   approximation ratio can be *measured*, not just bounded.

### 3.2 The greedy algorithm

```
GreedySetCover(R, U, c):
    U' ← U
    R' ← ∅
    while U' ≠ ∅:
        r ← argmax over r ∈ R \ R' of
              ( |S_r ∩ U'| / c(r) )          # best coverage per unit cost
        R' ← R' ∪ {r}
        U' ← U' \ S_r
    return R'
```

The selection criterion is **coverage per unit cost** — the density ratio. This is
the standard greedy for weighted set cover.

### 3.3 Why it fails: the greedy-choice property is absent

Greedy picks the rule covering the most uncovered obligations per unit cost. That
rule can be structurally wrong, because it consumes the universe elements that a
cheaper rule would have handled *for free* alongside its own.

**Counterexample (DocuTrace rule selection).** Four rules on universe
`U = {a, b, c, d, e, f}`, all costs equal to 1:

| Rule | Covers |
| --- | --- |
| `R_a` | `{a, b, c, d}` |
| `R_b` | `{e, f}` |
| `R_c` | `{a, b, e}` |
| `R_d` | `{c, d, f}` |

Greedy picks the largest first: `R_a` covers 4 elements. Then `R_b` covers the
remaining `{e, f}` in one more step. Greedy returns `{R_a, R_b}`, cost **2**.

The optimum is `{R_c, R_d}`, which covers `{a,b,e} ∪ {c,d,f} = U`, cost **2**.

Here greedy ties the optimum. Perturb the costs so that `R_a` is expensive —
`c(R_a) = 3`, everything else `1` — and the picture changes. Greedy still prefers
`R_a` (4/3 ≈ 1.33 per unit) over `R_c` (3/1 = 3.0)... so it picks `R_c` first,
covering `{a,b,e}`; then the best remaining is `R_d` (3/1), covering `{c,d,f}`;
universe done, cost **2**. Optimum is also 2.

The clean separating instance is the classic one below, where the optimal choice has
*maximum* coverage but greedy's density preference interacts badly:

**Separating instance.** `U = {1, …, 6}`. Rules:

| Rule | Covers | Coverage | Density (cost 1) |
| --- | --- | --- | --- |
| `R_1` | `{1, 2, 3, 4}` | 4 | 4.0 |
| `R_2` | `{1, 2, 5}` | 3 | 3.0 |
| `R_3` | `{3, 4, 6}` | 3 | 3.0 |

Greedy takes `R_1` (density 4.0). Remaining `{5, 6}`. No single rule covers both,
so two more picks are needed — say `R_2` then `R_3`. Greedy returns cost **3**.

Optimum: `{R_2, R_3}` covers `{1,2,5} ∪ {3,4,6} = U`, cost **2**. Greedy is 1.5×
the optimum on this instance.

This is exactly the mechanism: `R_1` grabs elements `{1,2,3,4}` that `R_2` and `R_3`
would have disposed of *incidentally*, and greedy has already spent its budget
before discovering that `5` and `6` are now orphaned. The choice was locally best
and globally wrong. **No exchange argument exists**, because no optimal solution
contains the greedy choice `R_1`.

The general form of this failure is the **`H(U)` lower bound**: greedy can be made
to achieve a ratio approaching `H(n) = Σ_{k=1}^{n} 1/k`, so its approximation
guarantee cannot be improved below the harmonic number.

### 3.4 The approximation guarantee

**Theorem G2 (`H(U)`-approximation).** Greedy weighted set cover returns a cover of
cost at most `H(U) · OPT`, where `H(U) = Σ_{k=1}^{|U|} 1/k ≤ ln|U| + 1`.

*Sketch (charging argument).* Order the elements by the step at which greedy first
covers them. Let `c_1, c_2, …` be the greedy costs. At step `i`, greedy covers
`|S_i ∩ U'_i|` new elements at cost `c(S_i)`, and by the density criterion,
*every* set in the optimum achieves no better density on `U'_i` than greedy's
chosen set:

```
c(S_i) / |S_i ∩ U'_i|  ≤  c(S*_j) / |S*_j ∩ U'_i|   for every S*
```

Summing the charge per element over greedy's picks, each element can be charged at
most `c(S*_j) · Σ_{k} 1/k` over the `|U'_i|` steps it survives, and summing over
the sets in the optimum telescopes to

```
cost(greedy) ≤ H(|U|) · Σ_{S* ∈ OPT} c(S*) = H(U) · OPT
```

Full charging argument in `CORRECTNESS_PROOFS.md` §13. ∎

**Tightness.** The bound is achievable: the standard construction lets greedy take
one large set of size `⌈|U|/2⌉`, then forces singletons, giving ratio exactly
`H(|U|/2)`. So `H(U)` is not an artifact of the proof — it is the true worst-case
performance of this greedy.

| `|U|` | `H(|U|)` | `ln|U| + 1` |
| --- | --- | --- |
| 8 | 2.718 | 3.079 |
| 16 | 3.381 | 3.773 |
| 64 | 4.744 | 5.159 |
| 256 | 6.124 | 6.545 |

For DocuTrace's actual obligation universe (`|U| ≈ 12–20` per template), the worst
case is a ratio under 4× on a cost measured in **sub-millisecond rule executions**.
The pipeline accepts it, and the Laboratory displays the measured ratio so the gap
is visible rather than hidden.

### 3.5 The exhaustive optimum (and its price)

For instances below the display threshold, DocuTrace enumerates all `2^|R|` subsets,
checks coverage, and keeps the cheapest. With `|R| = 8` (the current rule count)
that is 256 subsets — instant. The `2^|R|` ceiling is the reason this stays a
Laboratory feature and never enters the pipeline: `R` grows, and `2^|R|` does not
forgive. `NP_COMPLETENESS.md` §4 makes this argument precisely.

### 3.6 Complexity

| Solver | Time | Space | Guarantee |
| --- | --- | --- | --- |
| Greedy | `O(|R| · |U| · α)` where `α` = amortised density recomputation | `O(|R| + |U|)` | `≤ H(U)·OPT` |
| Exhaustive | `Θ(2^|R| · |U|)` | `O(|R| + |U|)` | exact |

In DocuTrace's implementation the greedy loop is `O(|R|² · |U|)` in the worst case
(each pick rescans all rules and recomputes coverage), which for `|R| ≤ 12`,
`|U| ≤ 32` is a few thousand operations — unmeasurable next to the document I/O
that surrounds it.

### 3.7 Determinism

Both solvers must return the same answer for the same input, or the Laboratory's
before/after comparison is meaningless. Two tie-breaks are therefore fixed in code:

1. **Equal density** → lower rule index wins (`R001` before `R002`).
2. **Equal cost in the exhaustive scan** → the lexicographically first subset in
   bitmask order wins.

`test_set_cover.py` asserts both, plus that the greedy result is never *better*
than the exhaustive optimum on any generated instance (a sanity property: an
approximation may tie the optimum but cannot beat it).

---

## 4. The two greedies side by side

| | Huffman | Greedy set cover |
| --- | --- | --- |
| Greedy choice | Merge two least-frequent symbols | Take best coverage-per-cost rule |
| Greedy-choice property | **Holds** (Lemma G1) | **Fails** (separating instance) |
| Optimal substructure | Holds (`Σ → Σ'`) | Holds |
| Result | **Optimal**, `Θ(n log n)` | **`H(U)`-approx**, `O(|R|²|U|)` |
| Certificate of quality | Kraft equality | Measured ratio vs exhaustive optimum |
| Where used | Intermediate compression | Rule selection in the pipeline |

The contrast is the pedagogical point of including both. The *same* paradigm
produces a provably optimal algorithm and a provably non-optimal one, and the only
difference is whether the greedy-choice property holds. Discharging that obligation
is the entire correctness argument in each case — an exchange argument in one, a
counterexample in the other.

---

## 5. Correctness enforcement in code

| Claim | Enforced by |
| --- | --- |
| Huffman produces a full binary tree with `n` leaves | `test_huffman.py::test_tree_is_full_and_has_n_leaves` |
| Kraft equality holds exactly | `test_huffman.py::test_kraft_equality` |
| Decoding round-trips the input | `test_huffman.py::test_roundtrip_random_frequencies` |
| Huffman cost ≤ fixed 8-bit encoding on skewed input | `test_huffman.py::test_beats_fixed_width_on_skew` |
| Greedy cover is indeed a cover | `test_set_cover.py::test_greedy_covers_universe` |
| Greedy never beats the exhaustive optimum | `test_set_cover.py::test_greedy_never_better_than_optimum` |
| The separating instance reproduces (greedy 3, optimum 2) | `test_set_cover.py::test_greedy_suboptimal_instance` |
| Deterministic tie-breaks | `test_set_cover.py::test_tie_breaks_are_deterministic` |

Each proof obligation above has a matching executable assertion. Where a claim is
only an approximation bound, the test checks the *bound*, not optimality — the
suite never asserts something the algorithm does not actually guarantee.

---

*See also:* `NP_COMPLETENESS.md` (why exhaustive set cover cannot scale),
`CORRECTNESS_PROOFS.md` §12–13 (full proofs), `RECURRENCE_RELATIONS.md` §8–9
(Huffman and set-cover recurrences), `ALGORITHM_COMPLEXITY.md` (aggregate pipeline
cost), `BENCHMARK_RESULTS.md` §4 (measured Huffman growth).
