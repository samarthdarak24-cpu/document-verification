# Correctness Proofs

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

Every algorithm in DocuTrace is implemented from scratch, so its correctness is
our responsibility, not a library's. This document proves each one correct, and
for the algorithms whose output can be checked mechanically, records the
cross-check that enforces the proof in code.

Two kinds of evidence appear throughout:

- **Proof** — a mathematical argument that the algorithm produces the required
  output for every valid input.
- **Enforcement** — the test that fails if the implementation diverges from the
  proof. A proof without an enforcement mechanism is a comment; this document
  pairs them.

Notation: `n`, `m` are input lengths; `V`, `E` graph size; `A`, `B` input
sequences; `A[i]` the i-th element (0-indexed); `A[0..i)` the prefix of length i.

---

## 1. Topological sort (Kahn's algorithm)

**Claim.** For a DAG `G = (V, E)`, Kahn's algorithm emits a permutation of V such
that for every edge `(u, v)`, `u` precedes `v`. If G contains a cycle, the
algorithm emits fewer than `|V|` vertices.

### Proof of the ordering property

Two lemmas.

**Lemma 1.1 — Every vertex is emitted.**
In a DAG, every subgraph has at least one vertex of in-degree 0. (Suppose not:
every vertex has an in-edge, so following in-edges backwards must revisit a
vertex, which is a cycle — contradicting that G is acyclic.) Therefore the queue
is never empty while unemitted vertices remain, so the loop continues until all
are emitted. ∎

**Lemma 1.2 — No edge is violated.**
Vertex `v` is enqueued only when its in-degree reaches 0, i.e. only after every
in-neighbour has been emitted (since the last decrement to 0 comes from the last
in-neighbour's emission). So every edge `(u, v)` has `u` emitted before `v` is
enqueued, hence before `v` is emitted. ∎

**Theorem 1.** By Lemma 1.1 all `|V|` vertices are emitted, and by Lemma 1.2 no
edge is violated. The emitted sequence is therefore a valid topological order. ∎

### Proof of the cycle detection

**Theorem 2.** If G has a cycle `v₁ → v₂ → … → v_k → v₁`, the algorithm emits at
most `|V| − k` vertices.

*Proof.* In a cycle, every `vᵢ` has an in-edge from `v_{i-1}` within the cycle. An
in-edge is only removed when its tail is emitted. So `v₁` cannot be enqueued until
`v_k` is emitted, `v_k` until `v_{k-1}`, …, and `v₂` until `v₁` — a circular
dependency. No vertex of the cycle can ever be enqueued, so at least k vertices
are never emitted. ∎

**Corollary.** After the queue empties, `len(order) < |V|` iff G contains a cycle.
This is the check DocuTrace performs, and it costs one integer comparison.

### Enforcement

`backend/tests/test_algorithms/test_topological_sort.py`:
- Every returned order is verified against *every* declared edge — not just that
  the length matches.
- Randomised DAGs are generated, topologically sorted, and re-checked.
- Cycles are constructed and asserted to be reported, never silently ordered.
- A specific test asserts determinism: the same DAG produces the same order on
  repeated runs (the property the audit trail depends on).

---

## 2. Merge sort

**Claim.** `merge_sort(A)` returns a permutation of A in non-decreasing order, and
is stable: elements comparing equal retain their relative input order.

### Proof of correctness

**Lemma 2.1 — `merge(L, R)` is correct.** Given sorted L and R, `merge` returns
the sorted concatenation of all their elements. By induction on `|L| + |R|`: the
smaller of `L[0]`, `R[0]` is the minimum of the union, so placing it first is
correct; the remainder is the same problem on a strictly smaller input. ∎

**Lemma 2.2 — `merge(L, R)` preserves stability.** When `L[0] == R[0]`, taking
`L[0]` keeps the earlier element first. Since L originally preceded R, and the
comparison uses `<=`, every equal pair keeps its input order. ∎

**Theorem 3.** By structural induction on `|A|`: for `|A| ≤ 1` the result is
trivially sorted and stable. For `|A| = n > 1`, the recursion sorts both halves
correctly and stably (induction hypothesis), and Lemma 2.1/2.2 combine them
correctly and stably. Hence the result is sorted and stable for all n. ∎

### Why stability is load-bearing here

In `duplicate_detection.py`, candidates are sorted by similarity score. Two
candidates can score identically (two byte-identical copies of the same original).
If the sort were unstable, which one is reported as "the best match" could vary
between runs, and the audit trail — `pipeline_order`, the recorded run, the
generated report — would no longer be reproducible. Stability makes the tie
break deterministic.

### Enforcement

`backend/tests/test_algorithms/test_sorting.py`:
- `sorted(input)` is the reference oracle; the outputs are compared exactly.
- Randomised arrays of varying length, including all-equal and already-sorted.
- **Stability** is tested with a keyed comparison on tagged tuples — two records
  with equal keys must come out in input order. A sort implementation that was
  accidentally unstable *fails* this test.

---

## 3. Quick sort (Lomuto partition)

**Claim.** `quick_sort(A)` returns A in non-decreasing order.

### Proof of the partition invariant

Lomuto's partition of `A[lo..hi]` with pivot `p = A[hi]` maintains the invariant
after each step of the loop over `j`:

```
A[lo..i]   ≤ p        (the "small" region)
A[i+1..j-1] > p       (the "large" region)
A[j..hi-1]  unexamined
A[hi]       = p       (pivot, in place)
```

**Initialisation.** Before the loop, `i = lo − 1` and `j = lo`, so both regions
are empty. The invariant holds vacuously.

**Maintenance.** If `A[j] ≤ p`, then swapping `A[++i]` with `A[j]` places the new
element at the end of the small region and moves the old `A[i]` (which was `> p`
or the boundary) into the large region. The regions grow by one each and the
invariant is restored. If `A[j] > p`, `j` simply advances and the element joins
the large region. Either way the invariant holds.

**Termination.** After the loop, `j = hi`, so the unexamined region is empty and
`A[hi] = p`. Swapping `A[i+1]` with `A[hi]` places p between the two regions, so
`A[lo..i] ≤ p < A[i+1..hi]`. ∎

**Theorem 4.** By induction on `hi − lo`: the base case (≤ 1 element) is
trivially sorted; the partition invariant places the pivot in its final sorted
position and splits the array into two strictly smaller subproblems which, by the
induction hypothesis, are each sorted. Concatenating two sorted subarrays around
a correctly-placed pivot yields a sorted array. ∎

### Enforcement

`backend/tests/test_algorithms/test_sorting.py`:
- Oracle comparison against `sorted()` on randomised and adversarial inputs.
- The classic worst cases (already sorted, reverse sorted, all equal) are tested
  explicitly — all-equal input is where a Lomuto partition with
  `A[j] <= pivot` degenerates, and the code must still be correct.
- Cross-check that quick sort and merge sort agree on the same input.

---

## 4. Binary search

**Claim.** For a sorted array A and target `t`, `binary_search` returns the index
of `t` if present, or reports absence, in O(log n).

### Proof via the loop invariant

**Invariant.** At the start of every iteration: if `t ∈ A`, then `t ∈ A[lo..hi]`.

**Initialisation.** `lo = 0`, `hi = n − 1`, so `A[lo..hi]` is all of A.

**Maintenance.** Let `mid = ⌊(lo+hi)/2⌋`.

- If `A[mid] == t`, the algorithm returns `mid`, which is correct.
- If `A[mid] < t`: A is sorted, so every element in `A[lo..mid]` is `≤ A[mid] < t`.
  Therefore `t` cannot lie in `A[lo..mid]`, so if present it lies in
  `A[mid+1..hi]`. Setting `lo = mid + 1` re-establishes the invariant.
- If `A[mid] > t`: symmetrically, `t` cannot lie in `A[mid..hi]`, so if present it
  lies in `A[lo..mid−1]`. Setting `hi = mid − 1` re-establishes the invariant.

**Termination.** Each iteration strictly shrinks `[lo, hi]`: either `lo` increases
past `mid` or `hi` decreases below `mid`. The interval is finite, so the loop
terminates. On termination `lo > hi`, so the interval is empty. By the invariant,
if `t` were present it would be in an empty interval — contradiction — so `t` is
absent, and reporting absence is correct. ∎

**Complexity.** The interval size after k iterations is at most `⌈(hi−lo+1)/2^k⌉`,
so termination occurs within `⌈log₂(n+1)⌉` iterations.

### Enforcement

`backend/tests/test_algorithms/test_binary_search.py`:
- Exhaustive check at small sizes: for every `n` up to a bound and every target,
  the returned index is compared against `list.index` semantics.
- Targets absent from the array are tested, including values below the minimum
  and above the maximum.
- Edge cases: empty array, single element, length 2.
- The reported pointer trace is checked to be monotone and consistent with the
  invariant.

---

## 5. Inversion counting

**Claim.** `count_inversions(A)` returns `|{(i, j) : i < j and A[i] > A[j]}|`.

### Proof

The algorithm is merge sort with one addition: during `merge`, when an element
from the right half is appended before elements remain in the left half, it adds
`len(left_remaining)` to the count.

**Every inversion is counted exactly once.**
An inversion `(i, j)` with `A[i] > A[j]` has `i`, `j` in either the same half or
different halves.

- *Different halves* (`i` left, `j` right): this pair is examined exactly once, at
  the merge level where the two halves are combined. At that moment, if `A[j]` is
  appended before `A[i]`, then `A[i]` is still in the remaining left half and is
  counted. Since `i < j` and left precedes right, `A[i] > A[j]` holds by
  assumption, so it *is* appended before. Counted once. ∎
- *Same half*: by the induction hypothesis, counted within the recursive call on
  that half.

**No non-inversion is counted.** When a right element is appended, every remaining
left element has not yet been placed, and merge places the smaller element first.
So each remaining left element is `> A[j]`, and `i < j` holds because all left
indices precede all right indices. So each counted pair is genuinely an inversion.
∎

**Theorem 5.** By induction: the base case (≤ 1 element) has no inversions. In the
inductive step, the two recursive calls count all same-half inversions correctly
(induction hypothesis) and the merge counts all cross-half inversions exactly once
(above). The total is the inversion count. ∎

### Enforcement

`backend/tests/test_algorithms/test_inversions.py`:
- Brute-force Θ(n²) double loop as the oracle, compared exactly on randomised
  arrays (n up to a few hundred so the oracle is tractable).
- The identity `sorted ⟺ 0 inversions` is asserted: an already-sorted array
  returns 0; a reverse-sorted array of n elements returns `C(n,2)`.
- Specific arrays with hand-computed counts, e.g. `[2, 4, 1, 3, 5] → 3`.

---

## 6. Bipartite matching (Edmonds–Karp)

**Claim.** The algorithm returns a maximum-cardinality matching.

### Proof

The correctness rests on Berge's theorem and the augmenting-path argument.

**Lemma 6.1 (Berge).** A matching M is maximum iff there is no M-augmenting path
(a path starting and ending at unmatched vertices whose edges alternate
not-in-M / in-M).

*Proof sketch.* (⟹) If an augmenting path exists, flipping its edges (in-M becomes
out, out becomes in) yields a matching with one more edge, so M was not maximum.
(⟸) If M is not maximum, let M* be larger. The symmetric difference `M ⊕ M*`
consists of alternating paths and cycles. Since `|M*| > |M|`, some component has
more M*-edges than M-edges — that component is an augmenting path for M. ∎

**Lemma 6.2 — The augmenting path found is valid.** BFS from all unmatched left
vertices explores alternating paths and stops at an unmatched right vertex. The
path returned alternates as required, so flipping it increases the matching by 1
and preserves the matching property (each vertex has at most one matched edge). ∎

**Theorem 6.** By Lemma 6.2, each augmentation increases `|M|` by exactly 1 while
keeping M a matching. The algorithm terminates when no augmenting path exists. By
Lemma 6.1, a matching with no augmenting path is maximum. ∎

**Termination.** `|M| ≤ min(|L|, |R|) ≤ V`, and each augmentation increases `|M|`,
so at most V augmentations occur. ∎

### The greedy counterexample this algorithm avoids

Consider labels `L = {L₁, L₂}`, definitions `D = {D₁, D₂}`, with:

- `L₁` an alias of both `D₁` and `D₂`
- `L₂` an alias of `D₁` only

A greedy assignment processing `D₁` first might take `L₁ → D₁`. Then `D₂` has no
remaining candidate and is reported as a **missing required field** — a false
rejection of a document that was complete. The maximum matching is
`{L₁ → D₂, L₂ → D₁}`, which satisfies both.

This exact configuration is a regression test in
`test_bipartite_matching.py`. It is the concrete reason a matching algorithm is
used rather than a greedy pass.

### Enforcement

`backend/tests/test_algorithms/test_bipartite_matching.py`:
- Maximum cardinality is verified against an exhaustive brute-force search for
  small graphs.
- The greedy-counterexample configuration is asserted to produce a perfect
  matching.
- Empty graphs, disconnected graphs, and complete bipartite graphs are tested.
- The returned matching is validated as a genuine matching: no label and no
  definition appears twice.

---

## 7. KMP

**Claim.** `kmp_search(text, pattern)` returns the starting index of every
occurrence of `pattern` in `text`, including overlapping occurrences.

### Proof of the LPS table

`lps[i]` is defined as the length of the longest proper prefix of `pattern[0..i]`
that is also a suffix of `pattern[0..i]`.

**Claim 7.1.** The table-building algorithm computes `lps` correctly.

*Proof.* The algorithm maintains that `lps[k]` is correct for all `k < i` and
that the current `len` equals `lps[i−1]` extended as far as possible. When
`p[i] == p[len]`, the prefix of length `len+1` extends to a prefix-suffix of
length `len+1`, and by the maximality of `lps[i−1]` this is the longest, so
`lps[i] = len+1`. When they differ, the algorithm falls back to `lps[len−1]`,
which is the next-longest candidate prefix-suffix by the definition of `lps`. It
repeats until a match or `len == 0`. Either the longest is found (and assigned) or
`len` reaches 0 (and `lps[i] = 0`, correct since no prefix-suffix exists). ∎

### Proof of the search

**Invariant.** At the top of each iteration, `pattern[0..j)` equals `text[i−j..i)`.

**Initialisation.** `i = j = 0`, both prefixes empty. Trivially holds.

**Maintenance.**
- On a match (`t[i] == p[j]`), both indices advance: `pattern[0..j+1)` now equals
  `text[i+1−(j+1)..i+1) = text[i−j..i+1)`. Invariant restored.
- On a mismatch with `j > 0`, the algorithm sets `j = lps[j−1]`. By the definition
  of `lps`, `pattern[0..lps[j−1])` is a suffix of `pattern[0..j)`, which by the
  invariant equals `text[i−j..i)`. So the new prefix still matches the text, and
  no position is skipped: any occurrence starting after `i − lps[j−1]` would
  require a shorter prefix-suffix, contradicting `lps` maximality. Invariant
  restored.
- On a mismatch with `j == 0`, `i` advances; nothing matched, invariant holds.

**Completion.** When `j == m`, the invariant gives `pattern[0..m)` =
`text[i−m..i)`, so there is an occurrence at `i − m`, which is recorded. `j` is
then set to `lps[m−1]` to continue searching for overlapping matches — this is why
`text = "aaaa", pattern = "aa"` finds indices 0, 1, 2 rather than only 0. ∎

**Completeness.** Every occurrence index is recorded: at the moment the scan
completes a match, `i − m` is exactly the start of an occurrence, and the scan
advances over every text position at which a match could end.

### Enforcement

`backend/tests/test_algorithms/test_kmp.py`:
- The reference oracle is `str.find` in a loop with `start = i + 1`, which permits
  overlaps — matching KMP's semantics.
- **200 randomised cross-checks** over an alphabet of size 3, with varying text
  and pattern lengths (including empty patterns and patterns longer than the
  text). Every match list is compared exactly.
- Adversarial input: `text = "aaaa…a"`, `pattern = "aaab"` — the case where naive
  search degrades to Θ(nm). KMP's result is asserted correct on it.
- Unicode: accented Latin (`café résumé`, with `é` matched at three code points)
  and CJK (`你好世界，你好` → matches at 0 and 5), confirming code-point rather
  than byte indexing.
- A test asserts the LPS table matches hand-computed values for the classic
  strings: `"ABABC" → [0,0,1,2,0]`, `"AAAA" → [0,1,2,3]`, `"AABAA" → [0,1,0,1,2]`.

---

## 8. Rabin–Karp

**Claim.** `rabin_karp(text, pattern)` returns exactly the set of occurrence
indices, with no false positives and no false negatives.

### Proof

**No false negatives.** If `pattern` occurs at position `i`, then `text[i..i+m)` is
character-identical to `pattern`, so their hashes are computed from identical
byte sequences with identical arithmetic — therefore equal. The window is
identified as a candidate and, by the verification step below, confirmed.
So every occurrence is found. ∎

**No false positives.** Every candidate whose hash matches is **verified character
by character** before being recorded. A window is only reported if it is literally
equal to the pattern. Hash collisions therefore cannot produce a false positive —
they merely cost an extra O(m) verification, which is the worst-case time term.
∎

**Hash rolling correctness.** With

```
h(i)   = Σ_{k=0}^{m-1} t[i+k] · b^(m-1-k)  mod q
h(i+1) = ( b · (h(i) − t[i]·b^(m-1)) + t[i+m] ) mod q
```

expanding gives `Σ_{k=0}^{m-1} t[i+1+k] · b^(m-1-k) mod q = h(i+1)`. The rolling
update is therefore exactly the window hash, computed in O(1). ∎

### Enforcement

`backend/tests/test_algorithms/test_rabin_karp.py`:
- Same randomised cross-check against the naive oracle as KMP.
- **A collision test**: an input is constructed for which two distinct windows
  share a hash, and the algorithm is asserted to report only the genuinely
  matching window. This is the test that would fail if the character-by-character
  verification were ever removed for performance.
- A cross-check that KMP and Rabin–Karp produce identical match lists on the same
  inputs — if they ever disagree, one is wrong.

---

## 9. SHA-256

**Claim.** The implementation computes SHA-256 exactly as specified by FIPS 180-4.

### Proof strategy

SHA-256 is a fixed procedure, not an algorithm with a correctness argument about
*classes* of inputs. Correctness is established by conforming to the specification
and by matching the published test vectors.

The implementation follows FIPS 180-4 §6.2:

1. **Padding.** Append a single `1` bit, then `k` zero bits, then the 64-bit
   big-endian length, where `k` is the smallest non-negative solution to
   `l + 1 + k ≡ 448 (mod 512)`.
2. **Message schedule.** For each 512-bit block, compute
   `W[0..15]` from the block and `W[16..63] = σ₁(W[t−2]) + W[t−7] + σ₀(W[t−15]) + W[t−16]`.
3. **Compression.** 64 rounds updating `(a,b,c,d,e,f,g,h)` with the standard
   constants `K[t]` and functions `Ch`, `Maj`, `Σ₀`, `Σ₁`.
4. **Output.** `H[0..7]` added to the round state, big-endian serialised.

**Streaming equivalence.** The implementation buffers input into 64-byte blocks
and processes a block only when it is full. Because the message schedule and
compression operate strictly per 512-bit block and the state `H` carries forward,
processing input in chunks produces byte-identical output to processing it all at
once. Padding is applied only at finalisation. Hence streaming is equivalent to
one-shot hashing. ∎

### Enforcement

`backend/tests/test_algorithms/test_hashing.py`:
- **Published test vectors**: the empty string, `"abc"`, the 448-bit message, and
  the million-`a` message from the FIPS/NIST vector set. These are the definitive
  check — if any constant, rotation, or shift were wrong, they would fail.
- **Streaming equivalence**: hashing a large input in one call is asserted equal
  to hashing it in chunks of varying sizes (1, 7, 63, 64, 65, 1000 bytes). This
  is the test that catches block-boundary bugs.
- Edge cases: exactly 55 bytes, 56 bytes, 63 bytes, 64 bytes, 65 bytes — the
  boundaries where padding crosses a block.
- Unicode input is encoded consistently (UTF-8) before hashing.

---

## 10. LCS (word-level DP)

**Claim.** `lcs(A, B)` returns the length of the longest common subsequence of A
and B, and with `matrix_available` the alignment that achieves it.

### Proof of optimal substructure

**Theorem 10.** The recurrence

```
L[i][j] = 0                                  if i = 0 or j = 0
L[i][j] = L[i-1][j-1] + 1                    if A[i-1] = B[j-1]
L[i][j] = max(L[i-1][j], L[i][j-1])          otherwise
```

computes the LCS length of `A[0..i)` and `B[0..j)`.

*Proof.* Let `A' = A[0..i)`, `B' = B[0..j)`.

*Case 1: `A[i-1] = B[j-1] = c`.* Let `S` be an LCS of `A'`, `B'` ending in `c`
(one exists: if an LCS of the same length does not end in the equal last
characters, appending them extends it, contradicting maximality). Then `S`
consists of an LCS of `A[0..i-1)`, `B[0..j-1)` followed by `c`, so
`L[i][j] = L[i-1][j-1] + 1`. ∎

*Case 2: `A[i-1] ≠ B[j-1]`.* Any common subsequence either does not use `A[i-1]`
(so it is a common subsequence of `A[0..i-1)` and `B'`, of length ≤ `L[i-1][j]`)
or does not use `B[j-1]` (length ≤ `L[i][j-1]`). It cannot use both, since they
differ. So `L[i][j] ≤ max(L[i-1][j], L[i][j-1])`. Conversely both candidates are
achievable, so equality holds. ∎

**Base case.** With an empty prefix there is no common subsequence, so the length
is 0. ∎

**Optimal substructure holds**, so the DP is valid; **overlapping subproblems
hold** (cell `(i,j)` is reached from both `(i−1,j)` and `(i,j−1)`), so tabulation
rather than recursion is appropriate.

### Correctness of the space-optimised variant

**Claim.** Two rows suffice for the length.

*Proof.* Every `L[i][j]` depends only on `L[i-1][j-1]`, `L[i-1][j]`, and
`L[i][j-1]` — that is, on the previous and current rows only. Filling row by row
and discarding older rows loses nothing. ∎

The reconstruction path is *not* available in this variant, which is why
DocuTrace keeps the full table when the alignment is required.

### Enforcement

`backend/tests/test_algorithms/test_lcs.py`:
- **Brute-force oracle**: for small inputs, enumerate all subsequences of the
  shorter string and check membership in the longer, taking the maximum length.
  Compared exactly.
- **Known values**: `LCS("ABCBDAB", "BDCABA") = 4`; identical strings give
  `length = n`; disjoint strings give 0; empty input gives 0.
- **Length-only equals full-table length**: the space-optimised and full-table
  variants are asserted to agree on randomised inputs — the test that catches a
  bug in the row-rotation logic.
- **Alignment validity**: the reconstructed alignment is asserted to be a genuine
  common subsequence (its tokens appear in order in both inputs) of exactly the
  reported length.

---

## 11. Edit distance (Levenshtein)

**Claim.** `edit_distance(A, B)` returns the minimum number of single-character
insertions, deletions and substitutions transforming A into B.

### Proof of optimal substructure

**Theorem 11.** The recurrence

```
D[i][0] = i,  D[0][j] = j
D[i][j] = D[i-1][j-1]                                  if A[i-1] = B[j-1]
D[i][j] = 1 + min(D[i-1][j], D[i][j-1], D[i-1][j-1])   otherwise
```

computes the minimum edit distance between `A[0..i)` and `B[0..j)`.

*Proof.* Any optimal edit sequence transforming `A' = A[0..i)` into `B' = B[0..j)`
ends in exactly one of three ways:

1. **Delete `A[i-1]`** then transform `A[0..i-1)` into `B'`: cost
   `1 + D[i-1][j]`.
2. **Insert `B[j-1]`** then transform `A'` into `B[0..j-1)`: cost
   `1 + D[i][j-1]`.
3. **Substitute (or match) `A[i-1]` with `B[j-1]`** then transform
   `A[0..i-1)` into `B[0..j-1)`: cost `D[i-1][j-1] + c` where `c = 0` if the
   characters are equal and `1` if not.

These are exhaustive: the last symbol of `B'` is produced either by deleting from
A, by inserting, or by consuming a symbol of A. Each case reduces to a strictly
smaller subproblem, so the optimum is the minimum over the three, which is exactly
the recurrence. ∎

**Distances are metric-like.** `D[i][i] = 0`, `D[i][j] = D[j][i]` (symmetry
follows because each operation has an inverse of equal cost and the recurrence is
manifestly symmetric). Both are asserted in tests.

### Correctness of the space-optimised variant

Identical argument to LCS: `D[i][j]` depends only on `D[i-1][j-1]`, `D[i-1][j]`,
`D[i][j-1]`, so two rows suffice for the distance. `with_operations=True` retains
the full table to backtrack the operation list.

### Enforcement

`backend/tests/test_algorithms/test_edit_distance.py`:
- **Brute-force oracle**: recursive search over all edit sequences with
  memoisation, for small strings. Compared exactly.
- **Known values**: `kitten → sitting = 3`; identical strings → 0; empty → length
  of the other; `"" → ""` → 0.
- **Symmetry**: `D(A,B) == D(B,A)` on randomised pairs.
- **Triangle inequality**: `D(A,C) ≤ D(A,B) + D(B,C)` on randomised triples.
- **Operations reconstruct the distance**: applying the returned operation list to
  A is asserted to produce B, and the operation count is asserted to equal the
  reported distance. This validates the backtracking, not just the count.
- **Length-only equals full-table**: same cross-check as LCS.

---

## 12. Huffman coding

**Claim.** Huffman coding produces a prefix-free code minimising
`Σ freq(c) · depth(c)`.

### Proof of the greedy-choice property

**Lemma 12.1.** Let `x` and `y` be the two least-frequent symbols. There exists an
optimal prefix-free code in which `x` and `y` are siblings at maximum depth.

*Proof.* Let T be an optimal tree. Let `a`, `b` be siblings at maximum depth in T,
and let `f(a) ≥ f(b)`, `f(x) ≥ f(y)` without loss of generality (by the choice of
x, y we have `f(x), f(y) ≤ f(a), f(b)`).

In T, swap `x` with `a`: the cost change is
`f(x)·depth(a) + f(a)·depth(x) − f(x)·depth(x) − f(a)·depth(a)`
`= (f(a) − f(x))·(depth(x) − depth(a)) ≤ 0`
since `f(a) ≥ f(x)` and `depth(a) ≥ depth(x)` (a is at maximum depth). So swapping
does not increase the cost. Now swap `y` with `b` similarly, obtaining a code no
worse than T in which `x` and `y` occupy the sibling positions of `a` and `b`, at
maximum depth. Since T was optimal, the result is optimal. ∎

**Lemma 12.2 (optimal substructure).** Let T′ be an optimal tree for the alphabet
with `x`, `y` replaced by a single symbol `z` of frequency `f(x) + f(y)`. Then
replacing the leaf `z` in T′ by an internal node with children `x` and `y` gives
an optimal tree for the original alphabet.

*Proof.* For any tree in which x and y are siblings:
`cost(T) = cost(T′) + f(x) + f(y)`, because the depths of x and y are each one
more than the depth of z would be, contributing exactly `f(x) + f(y)` extra. So
minimising `cost(T)` over such trees is equivalent to minimising `cost(T′)`. By
Lemma 12.1 an optimal tree exists among them, and by induction on alphabet size
T′ is optimal. ∎

**Theorem 12.** By induction on the alphabet size: the base case (one or two
symbols) is trivial. In the inductive step, Lemma 12.1 guarantees the greedy
choice (merge x, y) is part of some optimal solution, and Lemma 12.2 guarantees
that recursively solving the reduced problem and expanding yields an optimal
solution. Hence Huffman is optimal among prefix-free codes. ∎

### Prefix-freeness

Every symbol is a leaf in the code tree, and the code is the root-to-leaf path. A
leaf is never an ancestor of another leaf, so no codeword is a prefix of another.
Decoding is therefore unambiguous. ∎

This is asserted in tests: for every pair of codewords, neither is a prefix of the
other.

### The honest caveat

Optimality is with respect to the encoded payload only. The code table must be
transmitted to decode, and DocuTrace reports `table_size` and `net_saving`
alongside `compressed_size`, so a case where the table costs more than the payload
saves is reported as negative saving rather than as compression.

### Enforcement

`backend/tests/test_algorithms/test_huffman.py`:
- **Prefix-freeness**: asserted over all codeword pairs.
- **Round-trip**: encoding then decoding is asserted to reproduce the input
  exactly, for randomised inputs including empty, single-symbol, and
  highly-skewed frequency distributions.
- **Optimality vs brute force**: for small alphabets, all valid prefix-free codes
  are enumerated and the Huffman cost is asserted to be the minimum. This is the
  test that directly enforces Theorem 12 rather than merely checking a known
  answer.
- **Kraft equality**: the codeword lengths satisfy `Σ 2^(−len(c)) = 1`, which any
  optimal prefix-free code must.

---

## 13. Set cover

### 13.1 Exhaustive — proven optimal

**Claim.** Enumerating all 2^S subsets and returning the cheapest covering one
returns a minimum-cost cover.

*Proof.* The optimum is by definition the minimum over all subsets whose union
covers U. The enumeration visits every subset, discards exactly those that do not
cover U or that are marked invalid, and takes the minimum cost over the rest. By
construction the result is the optimum. ∎

This is trivially correct — its cost, not its correctness, is the reason it cannot
be the production path.

### 13.2 Greedy — approximation guarantee

**Claim.** The greedy algorithm (repeatedly take the set covering the most
uncovered elements per unit cost) returns a cover of cost at most `H(U) · OPT`,
where `H(U) = Σ_{i=1}^{U} 1/i` and `OPT` is the optimal cost.

**Proof sketch.** Let the uncovered elements be `U_t` before step `t`. Greedy
selects the set with the best coverage-per-cost ratio. Charging each newly covered
element `e` a share `cost(s) / |newly covered|` gives a total charge equal to the
greedy cost. For any element `e`, the set in an optimal cover that covers `e` had,
at the moment greedy considered the elements still uncovered, a ratio at least as
good as greedy achieved on that step (otherwise greedy would have chosen it, or it
had already been chosen). Summing over the harmonic series of remaining-uncovered
counts gives a total charge of at most `H(U) · OPT`. Since the charges sum to the
greedy cost, `greedy ≤ H(U) · OPT`. ∎

**Tightness.** Not merely a loose bound. On the instance where the universe is
partitioned into groups of sizes `⌊U/2⌋, ⌊U/4⌋, …, 1`, greedy takes the large group
first and then one group per step, achieving a cost ratio arbitrarily close to
`H(U)`. The bound is achieved, not just satisfied.

### 13.3 Why DocuTrace can do better than the bound

`OPT` is computable here because `S = 8`. DocuTrace therefore runs **both**:

- Greedy, as the production path (polynomial, guaranteed within `H(U)`).
- Exhaustive, to obtain `OPT` — cheap at `2^8 = 256` subsets.

With `OPT` known, greedy's actual performance is measured rather than assumed. In
every rule configuration DocuTrace can produce, greedy returns the optimum; the
`ln U` bound is a guarantee for arbitrary inputs, and here we do not need to rely
on it.

### Enforcement

`backend/tests/test_algorithms/test_set_cover.py`:
- **Greedy vs exhaustive**: on randomised instances, the greedy cover is asserted
  to (a) be a valid cover and (b) cost no more than `H(U)` times the optimum. This
  directly enforces the approximation guarantee.
- **Both cover U**: whichever path runs, the result is asserted to cover every
  element.
- **Optimality where expected**: on the rule configurations DocuTrace actually
  produces, greedy is asserted to equal the optimum.
- **Empty and degenerate inputs**: empty universe, a set covering everything, and
  an uncoverable universe (asserted to be reported as infeasible, not as an empty
  cover).

---

## 14. Cross-cutting invariants

Three properties are enforced globally, over and above any single algorithm.

### 14.1 Determinism

Two runs over identical input produce identical output. Enforced by running
algorithms twice and comparing results exactly, including the recorded trace. This
is why the pipeline's topological order sorts the in-degree-0 set at each layer:
determinism has to be designed in, not assumed.

### 14.2 Measurement honesty

Every result carries `comparisons`, `operations`, and `elapsed_ns`, and the tests
assert these are non-negative and consistent — an algorithm that reports zero
operations while returning a non-trivial result is failing a test, not passing one.

### 14.3 Purity

The 14 algorithm modules do not import anything from the application's database,
models, or services layer. Enforced by a test that inspects the import graph. This
is why they can be tested exhaustively in isolation, and why a bug in the pipeline
can never masquerade as a bug in an algorithm.

---

## 15. Summary

| Algorithm | Proof technique | Enforced by |
| --- | --- | --- |
| Topological sort | Invariant + lemma on in-degrees | Every edge checked on every order |
| Merge sort | Structural induction + stability lemma | Oracle compare + tagged stability test |
| Quick sort | Loop invariant + partition argument | Oracle compare + adversarial inputs |
| Binary search | Loop invariant | Exhaustive small-case compare |
| Inversions | Bijection (each inversion counted once) | Brute-force Θ(n²) oracle |
| Bipartite matching | Berge's theorem + augmenting paths | Exhaustive max-cardinality compare |
| KMP | LPS construction + search invariant | 200 randomised oracle checks |
| Rabin–Karp | Hash identity + verification step | Collision test + KMP cross-check |
| SHA-256 | FIPS 180-4 conformance | Published NIST vectors + streaming equivalence |
| LCS | Optimal substructure case analysis | Brute-force subsequence enumeration |
| Edit distance | Optimal substructure + last-operation analysis | Brute-force oracle + triangle inequality |
| Huffman | Exchange argument + optimal substructure | Brute-force optimal-code enumeration |
| Set cover (exhaustive) | Direct enumeration | Optimal by construction |
| Set cover (greedy) | Charging argument | Ratio bound + greedy-vs-optimal compare |
