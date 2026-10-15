# Algorithm Complexity Analysis

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

This document states the complexity of every algorithm in DocuTrace, derives the
bound rather than asserting it, and — where the benchmark data allows —
checks the derivation against measurement.

Notation: `n` and `m` are input sizes; `V` and `E` are graph vertices and edges;
`S` is the number of sets and `U` the universe size in set cover. `Θ` denotes a
tight bound, `O` an upper bound, `Ω` a lower bound.

---

## 1. Summary table

| # | Algorithm | Time (best) | Time (average) | Time (worst) | Space | Stable | In-place |
| - | --- | --- | --- | --- | --- | --- | --- |
| 1 | Topological sort (Kahn) | Θ(V+E) | Θ(V+E) | Θ(V+E) | Θ(V) | — | No |
| 2 | BFS traversal | Θ(V+E) | Θ(V+E) | Θ(V+E) | Θ(V) | — | No |
| 3 | DFS traversal | Θ(V+E) | Θ(V+E) | Θ(V+E) | Θ(V) | — | No |
| 4 | Merge sort | Θ(n log n) | Θ(n log n) | Θ(n log n) | Θ(n) | **Yes** | No |
| 5 | Quick sort (Lomuto, last pivot) | Θ(n log n) | Θ(n log n) | **Θ(n²)** | Θ(log n) expected | No | **Yes** |
| 6 | Binary search | Θ(1) | Θ(log n) | Θ(log n) | Θ(1) | — | Yes |
| 7 | Inversion counting | Θ(n log n) | Θ(n log n) | Θ(n log n) | Θ(n) | Yes | No |
| 8 | LCS (length only) | Θ(nm) | Θ(nm) | Θ(nm) | Θ(min(n,m)) | — | No |
| 9 | LCS (with alignment) | Θ(nm) | Θ(nm) | Θ(nm) | Θ(nm) | — | No |
| 10 | Edit distance (length only) | Θ(nm) | Θ(nm) | Θ(nm) | Θ(min(n,m)) | — | No |
| 11 | Edit distance (with ops) | Θ(nm) | Θ(nm) | Θ(nm) | Θ(nm) | — | No |
| 12 | KMP search | Θ(n+m) | Θ(n+m) | **Θ(n+m)** | Θ(m) | — | No |
| 13 | Rabin–Karp (expected) | Θ(n+m) | Θ(n+m) | Θ(nm) | Θ(1) | — | No |
| 14 | SHA-256 (streaming) | Θ(n) | Θ(n) | Θ(n) | Θ(1) | — | Yes |
| 15 | Huffman coding | Θ(n log n) | Θ(n log n) | Θ(n log n) | Θ(n) | — | No |
| 16 | Bipartite matching (Edmonds–Karp) | Θ(V·E) | Θ(V·E) | Θ(V·E) | Θ(V+E) | — | No |
| 17 | Set cover (greedy) | Θ(S·U) | Θ(S·U) | Θ(S·U) | Θ(U) | — | No |
| 18 | Set cover (exhaustive) | Θ(2^S·U) | Θ(2^S·U) | Θ(2^S·U) | Θ(S) | — | No |

---

## 2. Unit I — Graph and tree algorithms

### 2.1 Topological sort (Kahn's algorithm)

**Input:** a DAG with V vertices and E edges.
**Output:** a linear ordering where every edge `u → v` has `u` before `v`.

**Derivation.**

```
1. Compute in-degree of every vertex          O(V + E)     scan all edges once
2. Seed the queue with in-degree-0 vertices   O(V)         scan all vertices
3. While the queue is non-empty:
     dequeue u                                 O(1)         amortised, array queue
     append u to the order                     O(1)
     for each edge (u, v):
        in-degree[v] -= 1                      O(1)
        if in-degree[v] == 0: enqueue v        O(1)
                                              ─────────────
                                               O(V + E)     each vertex dequeued
                                                            once; each edge relaxed once
```

Every vertex enters the queue at most once and every edge is examined at most
once, so the total work is Θ(V + E).

**Cycle detection.** If the order contains fewer than V vertices when the queue
empties, a cycle exists. Detecting this costs nothing extra — it is a comparison
of two integers.

**DocuTrace instance.** V = 13 stages, E = 19 dependency edges. The bound is
irrelevant at this size (the measured stage time is 0.11 ms), but the algorithm's
*determinism* is not: sorting the in-degree-0 set at each layer makes the emitted
order reproducible, which is what allows `pipeline_order` to serve as an audit
record.

### 2.2 BFS and DFS traversal

Both visit each vertex once and each edge once:

```
BFS: Θ(V + E)   — every vertex enqueued at most once; every adjacency scanned once
DFS: Θ(V + E)   — every vertex entered at most once; every adjacency scanned once
```

**Space.** BFS holds the frontier, which in the worst case (a star graph) is
Θ(V). DFS holds the recursion stack, which in the worst case (a path graph) is
Θ(V). The iterative DFS in DocuTrace uses an explicit stack to avoid Python's
recursion limit on deep document hierarchies — the bound is identical, but the
constant factor and the failure mode are not.

---

## 3. Unit II — Divide and conquer

### 3.1 Merge sort

**Recurrence.** Splitting is O(1); merging two sorted halves of total size n is
Θ(n):

```
T(n) = 2·T(n/2) + Θ(n),    T(1) = Θ(1)
```

**Solving by the Master Theorem.** For `T(n) = a·T(n/b) + f(n)` with a = 2,
b = 2, f(n) = Θ(n):

```
log_b(a) = log_2(2) = 1
f(n) = Θ(n) = Θ(n^1) = Θ(n^(log_b a))
```

This is **case 2**, so `T(n) = Θ(n^(log_b a) · log n) = Θ(n log n)`.

**Across all levels.** The recursion tree has log₂ n levels. Level `i` contains
2^i subproblems of size n/2^i, each contributing Θ(n/2^i) work, so each level
contributes Θ(n) in total. Total: `Θ(n) × Θ(log n) = Θ(n log n)`, in **all three
cases** — the split is always exactly in half regardless of input order.

**Space.** The merge buffer holds Θ(n) elements. This is what makes merge sort
inapplicable where memory is tight, and it is the reason DocuTrace uses merge
sort for *ranking* (where a copy is acceptable) rather than for in-place work.

**Stability.** The merge step takes the left element when `left <= right`, never
`left < right`. That single `<=` is what makes the sort stable, and it is
load-bearing in DocuTrace: equal-score candidates must retain their input order
so the reported "best match" is reproducible across runs.

### 3.2 Quick sort (Lomuto partition, last-element pivot)

**Recurrence, balanced case.** If the pivot always splits into equal halves:

```
T(n) = 2·T(n/2) + Θ(n)  →  Θ(n log n)     (Master Theorem case 2)
```

**Recurrence, worst case.** Last-element pivot on already-sorted input splits
`n-1 : 0`:

```
T(n) = T(n-1) + T(0) + Θ(n) = T(n-1) + Θ(n)
     = Θ(n) + Θ(n-1) + ... + Θ(1)
     = Θ(n²)
```

**Why this is a feature here, not a bug.** The Laboratory *demonstrates* the
quadratic degradation: `/performance` plots quick sort and merge sort on an
already-sorted dataset, and the divergence is the visible result. The API accepts
`pivot: "last"` or `pivot: "random"`, so the randomised variant's expected
Θ(n log n) can be compared against the deterministic variant's worst case on the
same input.

**Space.** In-place partitioning uses O(1) auxiliary per call. With a
last-element pivot the recursion depth is Θ(n) in the worst case; with the
explicit-stack implementation and randomised pivot it becomes Θ(log n) expected.

### 3.3 Binary search

**Derivation by the loop invariant.** Invariant: if `target` is present, its
index lies in `[low, high]`. Each iteration halves the interval:

```
T(n) = T(n/2) + Θ(1)
```

Master Theorem: a = 1, b = 2, `log_b(a) = 0`, f(n) = Θ(1) = Θ(n^0) → **case 2** →
`T(n) = Θ(log n)`.

**Reality check.** The interval after k iterations has size `⌈n / 2^k⌉`, so the
loop terminates in `⌈log₂(n+1)⌉` iterations. For a sorted array of 1,000,000
elements that is 20 comparisons. Benchmark data confirms the shape: measured
times are 0.007 ms (n = 100) → 0.016 ms (n = 500) → 0.021 ms (n = 1,000) →
0.030 ms (n = 2,500) → 0.026 ms (n = 5,000). The curve is effectively flat
because the constant cost of the Python function call dominates, which is itself
the honest conclusion: at these sizes, log n is not the bottleneck.

**Precondition.** The input must be sorted. DocuTrace does not assume this — the
`/lab` workbench reports `sorted: false` and refuses to claim the result is
meaningful if the input violates the precondition.

### 3.4 Inversion counting

**Observation.** An array is sorted iff it has zero inversions. Rather than
counting pairs by brute force in Θ(n²), count them during a merge sort.

**Derivation.** In the merge step, when an element from the right half is taken
before elements remaining in the left half, those left elements are each
inverted with respect to it:

```
cross_inversions += (left_remaining)
```

Everything else is identical to merge sort, so the recurrence is unchanged:

```
T(n) = 2·T(n/2) + Θ(n)  →  Θ(n log n)
```

The alternative — a double loop over all pairs — is Θ(n²). For the section
reordering case with n sections, that is the difference between 10⁶ and 10⁶/20
operations at n = 1,000.

**Normalisation.** The maximum inversion count for n elements is C(n,2) =
n(n−1)/2. DocuTrace reports both the raw count and `normalized_reorder_score =
inversions / C(n,2)`, which is in [0, 1] and therefore comparable across
documents of different lengths.

---

## 4. Unit III — Dynamic programming and strings

### 4.1 Longest Common Subsequence

**Recurrence.**

```
L[0][j] = L[i][0] = 0
L[i][j] = L[i-1][j-1] + 1                  if A[i-1] == B[j-1]
L[i][j] = max(L[i-1][j], L[i][j-1])        otherwise
```

**Time.** The table has (n+1)(m+1) cells, each filled in Θ(1) → **Θ(nm)**.

**Space, full table.** Θ(nm) — required to reconstruct the alignment, because
reconstruction walks backwards and needs the predecessor of every cell.

**Space, length only.** The recurrence reads only `L[i-1][j-1]`, `L[i-1][j]`, and
`L[i][j-1]` — that is, the previous row and the current row. Keeping two rows of
width `min(n, m)` (iterate so the shorter string indexes the row) gives:

```
Θ(nm) time,  Θ(min(n, m)) space
```

At n = m = 1,000: 1,000,000 cells versus 2,000 — a 500× reduction, at the cost of
being unable to reconstruct the alignment.

**Which one DocuTrace uses.** The length-only form during candidate screening
(many comparisons, no alignment needed); the full table when the diff view must
show the matched spans (one comparison, alignment needed). This is exactly the
trade-off described above, applied per call site.

**Measured.** LCS median time is 0.094 ms (n = 100), 4.114 ms (n = 500), and
16.726 ms (n = 1,000). From 500 → 1,000 is a 2× size increase and a 4.07× time
increase, against 4× predicted by Θ(nm) for fixed m — the fit is essentially
exact.

### 4.2 Edit distance (Levenshtein)

**Recurrence.**

```
D[0][j] = j,   D[i][0] = i
D[i][j] = D[i-1][j-1]                                if A[i-1] == B[j-1]
D[i][j] = 1 + min(D[i-1][j], D[i][j-1], D[i-1][j-1]) otherwise
          │        │            │
          │        │            └─ substitute
          │        └─ insert
          └─ delete
```

**Time.** Θ(nm), same table-filling argument.

**Space.** Identical analysis to LCS: Θ(nm) with operations, Θ(min(n,m)) for the
distance alone. `with_operations=True` retains the full table and backtracks to
list the operations.

**Measured.** 0.155 ms (n = 100), 6.693 ms (n = 500), 22.641 ms (n = 1,000).
From 500 → 1,000: 3.38× against the predicted 4×.

**Why both LCS and edit distance.** They answer different questions.
`LCS = 8 of 10 words` says how much the documents share; `edit distance = 3, and
here are the operations` says exactly what changed and where. The field-drift
report needs the second.

### 4.3 KMP

**Building the LPS table.**

```
lps[0] = 0
for i = 1 to m-1:
    while len > 0 and p[i] != p[len]:  len = lps[len-1]
    if p[i] == p[len]: len += 1
    lps[i] = len
```

The `while` loop looks like it could make this quadratic, but it cannot: `len`
increases by at most 1 per iteration, so the total number of decreases across the
entire loop is bounded by the total number of increases, which is at most m. The
amortised cost is Θ(m). This is the classic amortised-argument mistake — a nested
loop is not automatically O(n²).

**Searching.**

```
i = 0 (text), j = 0 (pattern)
while i < n:
    if t[i] == p[j]:  i += 1; j += 1
    if j == m:        record match at i-j; j = lps[j-1]
    elif i < n and t[i] != p[j]:
        if j != 0: j = lps[j-1]
        else:      i += 1
```

The **text pointer `i` never decreases.** That is the invariant that makes KMP
linear. Total work is Θ(n) for the scan plus Θ(m) for the table:

```
Θ(n + m) in the worst case
```

**Contrast with naive search.** Naive on `text = "aaa...a"` (n a's) with
`pattern = "aa...ab"` (m−1 a's then b) compares m characters at each of n
positions → Θ(nm). KMP's LPS table makes the same input Θ(n + m). Repeated field
labels in a table-heavy document produce exactly this shape, which is why KMP is
the field-locator rather than a naive `find`.

**Measured.** KMP: 0.029 ms (n = 100) → 11.584 ms (n = 5,000). Linear scaling:
50× size, 399× time — superlinear only because of Python-level per-character
overhead at small n.

### 4.4 Rabin–Karp

**Rolling hash.** The hash of the window `t[i..i+m)` is

```
h(i) = (t[i]·b^(m-1) + t[i+1]·b^(m-2) + ... + t[i+m-1]) mod q
```

and the next window's hash is obtained in O(1):

```
h(i+1) = (b · (h(i) − t[i]·b^(m-1)) + t[i+m]) mod q
```

**Complexity.**

- Preprocessing: Θ(m) to compute the first hash and `b^(m-1) mod q`
- Scanning: Θ(n) windows × Θ(1) rolling update
- **Verification:** every hash match is confirmed character by character, Θ(m) each

If the number of hash matches is `v`, total time is **Θ(n + m + v·m)**.

- **Expected case:** with a well-chosen prime q and random input, the expected
  number of spurious matches is Θ(n/q), which is O(1) for q ≫ n. So:
  **Θ(n + m)** expected.
- **Worst case:** every window hashes to the target (possible with adversarial
  input, e.g. all identical characters). Then `v = n` and the time is
  **Θ(nm)**.

**Why the verification step is not optional.** Skipping it would make the
algorithm Θ(n + m) unconditionally — and *wrong*, because two different windows
can share a hash (a collision). DocuTrace never reports a match that has not been
verified character by character. The test suite constructs a colliding input and
asserts no false positive is produced.

**Measured.** Rabin–Karp is consistently slower than KMP in DocuTrace's benchmarks
(1.717 ms vs 0.029 ms at n = 100; 149.588 ms vs 11.584 ms at n = 5,000), because
the per-window Python arithmetic outweighs KMP's table lookup. Rabin–Karp earns
its place when searching for *many* patterns simultaneously, where one pass over
the text amortises the rolling hash across all patterns; for a single pattern, KMP
wins. The Laboratory reports both so the comparison is measurable rather than
asserted.

### 4.5 SHA-256 (streaming)

**Time.** Θ(n). Each 64-byte block costs 64 rounds of constant work, so the total
is proportional to the input length (plus padding to a block boundary). SHA-256 is
not a search or a sort; there is no better case to distinguish.

**Space.** Θ(1) auxiliary. The implementation holds one 64-byte block buffer and
an 8-word state, regardless of input size — that is what makes it *streaming*.
The file is read in chunks and never fully materialised in memory, so hashing a
2 GB file uses the same working memory as hashing a 2 KB one.

**Why hash at all.** Two files with the same SHA-256 are byte-identical with
overwhelming probability (the collision resistance of the construction makes a
forged collision computationally infeasible). DocuTrace uses this as the *cheapest
and most certain* duplicate test, so it runs before any DP: the `EXACT_DUPLICATE`
case for sample `02` is decided by hash equality, in constant time, with no
similarity scoring at all.

Two hashes are maintained per document:

1. **`file_sha256`** — the raw bytes. Equal ⟹ byte-identical file.
2. **`normalized_text_hash`** — the canonicalised text. Equal ⟹ semantically
   identical content reaching the verifier, even if the file wrapper differs
   (e.g. a re-exported PDF that renders the same text).

The two together separate "the same file" from "the same content" from "similar
content" — three genuinely different situations that a single score would
conflate.

---

## 5. Unit IV — Huffman coding

**Derivation.** With n distinct symbols, the algorithm performs n − 1 merges.
Using a binary min-heap:

| Step | Cost |
| --- | --- |
| Build the heap from n symbol frequencies | Θ(n) (heapify) |
| Each of n−1 extractions | Θ(log n) |
| Each of n−1 insertions of the merged node | Θ(log n) |

Total:

```
Θ(n) + (n − 1)·Θ(log n) + (n − 1)·Θ(log n) = Θ(n log n)
```

A naive implementation that scans for the two minima on each iteration is Θ(n²);
the heap is what buys the log factor.

**Space.** Θ(n) for the heap and the node table.

**Correctness of the greedy choice.** Huffman's optimality rests on two lemmas:

1. *Greedy-choice property.* There exists an optimal prefix-free code in which
   the two least-frequent symbols are siblings at maximum depth. (Exchange
   argument: if they are not, swap them with the deepest siblings and the cost
   does not increase.)
2. *Optimal substructure.* Merging the two least-frequent symbols and solving the
   resulting (n−1)-symbol problem yields an optimal n-symbol code.

**The honest caveat.** Huffman minimises `Σ freq(c) · depth(c)` — the encoded
payload. It says nothing about the code table, which must be stored to decode.
DocuTrace reports:

```
compressed_size, table_size, net_saving = uncompressed_size − compressed_size − table_size
```

For a short document with a broad alphabet the table can exceed the payload
saving, and `net_saving` goes negative. Reporting the ratio without the table
would be a false claim of compression; the API reports all three.

---

## 6. Unit V — Bipartite matching

**Problem.** Given a bipartite graph with `|L|` labels and `|R|` definitions and
`E` candidate edges, find a matching of maximum cardinality.

**Algorithm.** Edmonds–Karp: repeatedly find a shortest augmenting path with BFS
and augment along it.

**Derivation.**

- Each augmentation increases the matching size by exactly 1, so at most
  `min(|L|, |R|)` augmentations are needed — at most `O(V)`.
- BFS from all unmatched left vertices costs Θ(V + E).
- Total: **Θ(V · (V + E)) = Θ(V · E)** for a sparse graph where `E = Ω(V)`.

**Why BFS rather than DFS.** Both find augmenting paths, but BFS finds *shortest*
ones, which bounds the number of augmentations by the shortest-path structure and
gives the polynomial bound above. A DFS-based search can require exponentially
many augmentations on adversarial inputs.

**Flow formulation.** Maximum bipartite matching is the integral special case of
max-flow:

```
source → each label       capacity 1
label  → definition       capacity 1   (one per candidate edge)
definition → sink         capacity 1
```

Because every capacity is integral, the augmenting-path search produces an
integral maximum flow, and the set of saturated `label → definition` edges is a
maximum matching.

**Why not greedy.** A greedy assignment can produce a strictly smaller matching
and therefore report a required field as missing when a valid assignment existed.
See `CORRECTNESS_PROOFS.md` §6 for the concrete counterexample used as a
regression test.

---

## 7. Unit VI — Set cover

**Problem (weighted).** Given a universe U, a family of sets `S₁..Sₛ` each
covering a subset of U with associated cost, find a minimum-cost subfamily whose
union is U.

**Complexity.** The decision version is NP-complete (membership in NP is by
verifying a candidate cover in polynomial time; NP-hardness is by reduction from
Vertex Cover). Therefore no polynomial-time exact algorithm is known.

### 7.1 Greedy (production path)

Repeatedly select the set maximising `|uncovered ∩ Sᵢ| / cost(Sᵢ)`.

```
Each pass scans all S sets over at most U elements   Θ(S · U)
At most min(S, U) passes                             Θ(min(S,U))
Total                                                Θ(S · U · min(S, U))
```

**Approximation ratio.** `H(U) = Σ_{i=1..U} 1/i = ln U + O(1)`, i.e. the greedy
cover costs at most `(ln U + 1)` times the optimum.

**Tightness.** The bound is achievable: on the classic construction where the
universe is partitioned into groups of geometrically decreasing size, greedy
performs strictly worse than optimal by exactly the harmonic factor. The ratio is
not an artifact of loose analysis.

### 7.2 Exhaustive (validation path)

Enumerate all 2^S subsets, check coverage, keep the cheapest.

```
Θ(2^S) subsets × Θ(U) coverage check = Θ(2^S · U)
```

**DocuTrace's instance.** S = 8 rules, U = the small set of observable symptoms.
`2^8 = 256` subsets — trivially enumerable. So the exact optimum is computable,
and the test suite asserts greedy is never worse than it. It never is.

**The engineering point.** Recognising that set cover is NP-complete does three
things: it says stop looking for a polynomial exact algorithm; it motivates
bounding the instance so an exact algorithm stays feasible; and it justifies
keeping a polynomial approximation on hand in case the instance grows. DocuTrace
does all three, and — because its instance is small — it can *verify* rather than
assume the approximation quality.

---

## 8. Aggregate pipeline complexity

One upload runs the pipeline. Let:

- `N` = total extracted character count
- `W` = word-token count, `W ≤ N`
- `C` = number of candidate documents retrieved for comparison
- `K` = number of template field labels/aliases
- `D` = `DP_MAX_TOKENS` (the DP cap, default 2000)

| Stage | Complexity |
| --- | --- |
| Scheduling | Θ(V + E), V = 13, E = 19 |
| File validation | Θ(N) (magic bytes are O(1); SHA-256 over the file is Θ(file size)) |
| Text extraction | Θ(N) for native text; OCR is Θ(pixels) and dominates when used |
| Normalisation | Θ(N) |
| Candidate retrieval | Θ(W) per indexed document (token-set intersection) |
| Field detection | Θ(K · N) for K alias searches over N characters, KMP over the whole text |
| Field validation | Θ(K · V_field · E_field) for the matching |
| Hashing | Θ(N) |
| Duplicate lookup | Θ(C) hash lookups |
| Similarity analysis | **Θ(C · D²)** — the dominant term |
| Structural validation | Θ(S log S) for S sections |
| Verification decision | Θ(2^R · U), R = 8 rules |
| Report generation | Θ(N + R + C) |

**Total:** `Θ(N + K·N + K·V·E + C·D² + S log S + 2^R·U)`.

The dominant term is `C · D²` — the DP comparisons. That is why `DP_MAX_TOKENS`
exists: it is the one term that can grow without bound, and capping it converts an
unbounded cost into a fixed one. The trade-off is explicit in the response
(`truncated`, `truncation_note`) rather than hidden.

---

## 9. Predicted vs measured

Every derived bound above is checkable. The engineering discipline is to check
it, because a complexity derivation that disagrees with measurement means one of
them is wrong.

**Size-doubling test.** For a Θ(n log n) algorithm, doubling n should multiply the
time by a factor approaching 2·(1 + 1/log n) ≈ 2.2–2.6 for the sizes below. For
Θ(n²), by 4. For Θ(log n), by ~1.

From the measured medians (ms):

| Algorithm | n=500 | n=1000 | Ratio | Predicted | Verdict |
| --- | --- | --- | --- | --- | --- |
| Merge sort | 4.569 | 9.630 | 2.11 | ~2.2–2.6 | Consistent |
| Inversion counting | 4.308 | 11.235 | 2.61 | ~2.2–2.6 | Consistent |
| KMP | 0.693 | 1.828 | 2.64 | ~2.2–2.6 | Consistent |
| Rabin–Karp | 9.313 | 19.670 | 2.11 | ~2.2–2.6 | Consistent |
| LCS | 4.114 | 16.726 | 4.07 | ~4.0 (Θ(nm)) | Consistent |
| Edit distance | 6.693 | 22.641 | 3.38 | ~4.0 (Θ(nm)) | Consistent |
| Binary search | 0.016 | 0.021 | 1.31 | ~1.1 (Θ(log n)) | Consistent |

Every measured ratio lands within the range its derived bound predicts. Complete
data, more sizes, and all five sizes per algorithm are in
[`BENCHMARK_RESULTS.md`](BENCHMARK_RESULTS.md).

---

## 10. Space complexity summary

| Structure | Space | Notes |
| --- | --- | --- |
| LCS length-only | Θ(min(n,m)) | Two rows |
| LCS full table | Θ(nm) | Needed for alignment reconstruction |
| Edit distance length-only | Θ(min(n,m)) | Two rows |
| Edit distance with ops | Θ(nm) | Needed for the operation list |
| Merge sort | Θ(n) | Merge buffer |
| Quick sort | Θ(log n) expected | Explicit stack; Θ(n) with a last-element pivot on sorted input |
| Merge sort on disk | Θ(n) | Full copy of the input |
| Inversion counting | Θ(n) | Merge buffer |
| KMP | Θ(m) | LPS table |
| Rabin–Karp | Θ(1) | One hash + one power |
| SHA-256 | Θ(1) | 64-byte block buffer + 8-word state |
| Huffman | Θ(n) | Heap + node table |
| Bipartite matching | Θ(V + E) | Adjacency + match arrays |
| Set cover greedy | Θ(U) | Coverage flags |
| Inversion counting | Θ(n) | Merge buffer |
| Pipeline (peak) | Θ(N + D²) | Text plus the DP table |

**Peak pipeline space** is dominated by the extracted text (Θ(N)) and, when the
full DP table is materialised, Θ(D²) = Θ(4·10⁶) cells at the default cap. That is
the largest single allocation in the system and the reason `D` is configurable.

---

## 11. Conclusion

The complexity work in DocuTrace is not decoration. Three specific decisions were
driven by it:

1. **KMP over naive search** for field labels, because the adversarial case is the
   common case for tabulated documents (§4.3).
2. **Bounded DP with explicit truncation reporting**, because `C · D²` is the only
   unbounded term in the pipeline (… and hiding a truncated comparison would
   produce a silently wrong score).
3. **Greedy set cover in production with exhaustive validation in tests**, because
   the general problem is NP-complete but the actual instance is 2⁸ (§7).

Each is a place where knowing the bound changed what the code does.
