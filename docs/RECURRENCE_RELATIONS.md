# Recurrence Relations

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

Every recursive algorithm in DocuTrace has a running time described by a
recurrence. This document states each recurrence, solves it by the method best
suited to its shape, and — for the divide-and-conquer cases — verifies the
solution by the substitution method as well as by the Master Theorem, so the
answer does not depend on one technique being applied correctly.

---

## 1. Methods used

### 1.1 The substitution method

Guess a bound, prove it by induction on the input size, and resolve the constants.

Procedure:
1. Guess the form (e.g. `T(n) = O(n log n)`).
2. Assume the bound holds for all `m < n`.
3. Substitute the inductive hypothesis into the recurrence.
4. Choose constants so the result matches the guess.
5. Check the base case.

This method works on recurrences the Master Theorem cannot handle, and it exposes
the constants the Master Theorem hides. It is used here as the primary check.

### 1.2 The Master Theorem

For `T(n) = a·T(n/b) + f(n)` with `a ≥ 1`, `b > 1`, and comparing `f(n)` against
`n^(log_b a)`:

| Case | Condition | Result |
| --- | --- | --- |
| 1 | `f(n) = O(n^(log_b a − ε))` for some ε > 0 | `T(n) = Θ(n^(log_b a))` |
| 2 | `f(n) = Θ(n^(log_b a) · log^k n)` for k ≥ 0 | `T(n) = Θ(n^(log_b a) · log^(k+1) n)` |
| 3 | `f(n) = Ω(n^(log_b a + ε))` and the regularity condition holds | `T(n) = Θ(f(n))` |

Directly applicable to merge sort, quick sort's balanced case, binary search, and
inversion counting.

### 1.3 The recursion-tree method

Draw the tree of subproblem sizes, sum the work per level, and sum across levels.
Used here to corroborate the Master Theorem results and to make the "why" visible.

### 1.4 Characteristic equations (for linear recurrences)

For recurrences like `T(n) = T(n−1) + f(n)` arising from decrement-and-conquer,
unrolling is the natural method: expand until the base case, then sum the series.

---

## 2. Merge sort

### The recurrence

Splitting at the midpoint costs Θ(1); merging two sorted halves totals Θ(n):

```
T(n) = 2·T(n/2) + Θ(n),      T(1) = Θ(1)
```

### Solution by the Master Theorem

```
a = 2,  b = 2,  f(n) = Θ(n)
log_b(a) = log₂ 2 = 1
n^(log_b a) = n^1 = n
f(n) = Θ(n) = Θ(n^(log_b a))
```

`f(n)` matches `n^(log_b a)` exactly, so this is **case 2** with `k = 0`:

```
T(n) = Θ(n^(log_b a) · log^(k+1) n) = Θ(n · log n)
```

### Verification by substitution

**Claim.** `T(n) = O(n log n)`.

*Proof.* Assume `T(m) ≤ c·m·log m` for all `m < n`. Then

```
T(n) ≤ 2·c·(n/2)·log(n/2) + d·n
     = c·n·(log n − log 2) + d·n
     = c·n·log n − c·n + d·n
     = c·n·log n − (c − d)·n
     ≤ c·n·log n                provided c ≥ d
```

Choose `c ≥ d` and the induction closes. The base case `T(1) = Θ(1)` is absorbed
by choosing `c` large enough. Hence `T(n) = O(n log n)`. ∎

**Claim.** `T(n) = Ω(n log n)`.

*Proof.* With `T(m) ≥ c·m·log m`:

```
T(n) ≥ 2·c·(n/2)·log(n/2) + d·n = c·n·log n − (c − d)·n
```

which is `≥ c·n·log n` when `c ≤ d`. ∎

Combining both, `T(n) = Θ(n log n)`.

### Verification by recursion tree

Level `i` contains `2^i` subproblems of size `n/2^i`. Each contributes `c·n/2^i`
work, so the level total is `2^i · c·n/2^i = c·n`. There are `log₂ n` levels
before subproblems reach size 1, plus the leaf level at size 1 contributing `c·n`
in total. So:

```
T(n) = c·n + c·n + … + c·n        (log₂ n + 1 levels)
     = c·n·(log₂ n + 1)
     = Θ(n log n)
```

The per-level sum being **constant** is the structural reason the answer is `n log n`
rather than `n²`: the halving of work per subproblem exactly offsets the doubling
of subproblem count.

### In DocuTrace

Merge sort ranks similarity candidates. At n = 1,000 candidates:

```
n log₂ n = 1000 × 9.97 ≈ 9,970 comparison-level operations
n²       = 1,000,000            — 100× worse
```

Measured: 4.569 ms at n = 500 and 9.630 ms at n = 1,000, a ratio of 2.11 against
the `log` factor's prediction. See `ALGORITHM_COMPLEXITY.md` §9.

---

## 3. Quick sort

### The recurrence — best and average case

When the pivot splits the array into two halves of size roughly `n/2`:

```
T(n) = 2·T(n/2) + Θ(n)
```

Identical to merge sort, so by the same Master Theorem case-2 argument:

```
T(n) = Θ(n log n)
```

### The recurrence — worst case

With a last-element pivot on already-sorted input, every split is `(n−1, 0)`:

```
T(n) = T(n−1) + T(0) + Θ(n) = T(n−1) + Θ(n)
```

**Solution by unrolling.**

```
T(n) = T(n−1) + c·n
     = [T(n−2) + c(n−1)] + c·n
     = T(n−2) + c(n−1) + c·n
     = …
     = T(1) + c·Σ_{i=2}^{n} i
     = Θ(1) + c·(n(n+1)/2 − 1)
     = Θ(n²)
```

The sum is arithmetic, so the answer is quadratic.

### The average case, briefly

If pivots are uniformly random ranks, the expected number of comparisons is

```
E[C(n)] = 2n·H(n) − 4n ≈ 2n·ln n
```

derived by summing, over all pairs `(i, j)`, the probability that they are compared
— which is `2/(j − i + 1)`. Summing the harmonic series gives `Θ(n log n)`. The
constant `2 ln 2 ≈ 1.39` makes the expected comparison count about 39% higher than
merge sort's, which is why DocuTrace uses merge sort for the ranking path where the
extra comparisons matter.

### In DocuTrace

The randomised-pivot variant accepts `pivot: "random"` so the expected and worst
cases can be compared in `/performance` on the *same* input. That comparison —
the two curves diverging on already-sorted data — is the pedagogical point of
including quick sort at all.

---

## 4. Binary search

### The recurrence

One comparison, then a single subproblem half the size:

```
T(n) = T(n/2) + Θ(1),      T(1) = Θ(1)
```

### Solution by the Master Theorem

```
a = 1,  b = 2,  f(n) = Θ(1)
log_b(a) = log₂ 1 = 0
n^(log_b a) = n^0 = 1
f(n) = Θ(1) = Θ(n^(log_b a))
```

Case 2 with `k = 0`:

```
T(n) = Θ(n^0 · log n) = Θ(log n)
```

### Verification by unrolling

```
T(n) = T(n/2) + c
     = T(n/4) + 2c
     = T(n/2^k) + k·c
```

Terminates when `n/2^k = 1`, i.e. `k = log₂ n`:

```
T(n) = T(1) + c·log₂ n = Θ(log n)
```

### The exact iteration count

The interval after k iterations has size `⌈n/2^k⌉`, so the loop runs at most
`⌈log₂(n+1)⌉` times. For `n = 1,000,000` that is 20 iterations. Measured DocuTrace
times (0.007 ms at n = 100 → 0.026 ms at n = 5,000) are dominated by Python's
per-call overhead rather than by the `log n` term, which is the honest reading of
that data.

---

## 5. Inversion counting

### The recurrence

Identical to merge sort, because it *is* merge sort with a counter:

```
T(n) = 2·T(n/2) + Θ(n)
```

The counting adds `Θ(1)` per merge step (one integer addition), absorbed into the
merge cost.

### Solution

By the Master Theorem, case 2:

```
T(n) = Θ(n log n)
```

By substitution: the same inductive argument as merge sort applies, since the
recurrence is the same. The extra `Θ(1)` per step changes the constant, not the
class.

### Contrast with the naive approach

Counting inversions by examining every pair:

```
T(n) = Θ(n²)
```

For n = 1,000 sections that is 499,500 pair comparisons versus roughly 10,000
merge-level operations — a 50× difference, and it grows.

### Why the merge sort structure is the right host

An inversion `(i, j)` with `i < j` and `A[i] > A[j]` has its two indices either in
the same half or in different halves. Merge sort's structure hands you exactly the
partition needed to count each cross-half inversion once, at the moment of
comparison, at no extra asymptotic cost. Recognising that an existing algorithm's
structure already contains the information you need — rather than writing a second
pass — is the transferable idea.

---

## 6. Longest Common Subsequence

### The recurrence

LCS is not naturally expressed as a size-halving recurrence; it is a **2D
dynamic-programming recurrence**. The relevant "recurrence" is the cell relation:

```
L[i][j] = 0                                       if i = 0 or j = 0
L[i][j] = L[i-1][j-1] + 1                         if A[i-1] = B[j-1]
L[i][j] = max(L[i-1][j], L[i][j-1])               otherwise
```

### Work count

The table has `(n+1) × (m+1)` cells, each filled in `Θ(1)`:

```
T(n, m) = Θ(n·m)
```

There is no recursion to solve — the recurrence *is* the algorithm, evaluated
bottom-up.

### Why the naive recursive formulation is exponential

If implemented as literal recursion following the recurrence:

```
T(n, m) = T(n-1, m) + T(n, m-1)          (mismatch case)
```

*Solution.* This is the same recurrence as counting monotone lattice paths. The
number of paths from `(n, m)` to the boundary is `C(n+m, n)`, so:

```
T(n, m) = Θ(C(n+m, n)) = Θ(2^(n+m) / √(n+m))
```

Exponential. For n = m = 30 that is about `C(60,30) ≈ 1.18 × 10^17` calls.

**The fix is memoisation or tabulation**, which collapses the exponential tree into
`n·m` distinct states. This is the definitional illustration of *overlapping
subproblems*: the exponential blowup comes entirely from recomputing the same
`(i, j)` state. Tabulation makes the state space explicit and fills each once:

```
recursive:   Θ(2^(n+m) / √(n+m))       exponential
memoised:    Θ(n·m)                    polynomial
```

That gap is the *only* reason dynamic programming exists, and it is why DocuTrace
implements LCS as a table rather than a recursive function.

### Space recurrence

Full table: `S(n, m) = Θ(n·m)`.
Two-row variant: `S(n, m) = Θ(min(n, m))`, since only the previous and current rows
are live.

---

## 7. Edit distance

### The recurrence

```
D[i][j] = D[i-1][j-1]                                if A[i-1] = B[j-1]
D[i][j] = 1 + min(D[i-1][j], D[i][j-1], D[i-1][j-1]) otherwise
D[i][0] = i,   D[0][j] = j
```

### Work count

Same `(n+1) × (m+1)` table, each cell `Θ(1)`:

```
T(n, m) = Θ(n·m)
```

### The naive recursion is also exponential

Following the recurrence literally on mismatches gives the three-way branching

```
T(n, m) = T(n-1, m) + T(n, m-1) + T(n-1, m-1)
```

which is asymptotically *worse* than the two-way LCS recursion. Bounding it:

```
T(n, m) ≥ 3^min(n,m)        (lower bound, since each step branches at least 3-ways)
```

So `T(n, m) = Ω(3^min(n,m))` — strictly worse than LCS's naive form. Memoisation
again collapses it to `Θ(n·m)`.

### Space recurrence

Identical structure to LCS: `Θ(n·m)` with operations, `Θ(min(n, m))` for the
distance alone. The same two-row argument applies because `D[i][j]` reads only
`D[i-1][·]` and `D[i][j-1]`.

---

## 8. Huffman coding

Huffman is not divide-and-conquer; its cost recurrence comes from the heap-driven
loop. There are `n − 1` merges, and each merge performs two extractions and one
insertion on a binary heap:

```
T(n) = Θ(n)                        heap construction (heapify)
     + (n − 1) · [ 2·Θ(log n) + 1·Θ(log n) ]     merges
     = Θ(n) + Θ(n log n)
     = Θ(n log n)
```

If the two minima were found by linear scan instead:

```
T(n) = Θ(n) + (n − 1)·Θ(n) = Θ(n²)
```

The heap is what converts the quadratic into `n log n`.

### The recurrence for the cost, not the time

The *weighted path length* of the Huffman tree satisfies its own recurrence. Let
`C(A)` be the minimum cost for alphabet A:

```
C(A) = C(A \ {x, y} ∪ {z}) + f(x) + f(y),     where f(z) = f(x) + f(y)
C({s}) = 0
```

and `x`, `y` are the two least-frequent symbols. This is the optimal-substructure
statement proved in `CORRECTNESS_PROOFS.md` §12, and solving it bottom-up is
exactly what the algorithm does — so the algorithm's structure *is* the
recurrence's solution.

---

## 9. Bipartite matching (Edmonds–Karp)

The augmentation loop yields a recurrence in the number of augmentations, not in a
halved input size:

```
T(V, E) = (number of augmentations) × (cost per augmentation)
```

- Each augmentation increases `|M|` by exactly 1, and `|M| ≤ min(|L|, |R|) ≤ V`, so
  at most `V` augmentations.
- Each augmentation runs one BFS, which is `Θ(V + E)`.

Therefore:

```
T(V, E) = O(V · (V + E)) = O(V · E)      for sparse graphs where E = Ω(V)
```

### Why the recurrence is well-founded

There is no "halving" here — the termination argument is that `|M|` strictly
increases and is bounded above by `V`. A recurrence with a monotone increasing
bounded measure is the standard form for augmentation algorithms, and it is why
the bound is `V` times a BFS rather than something logarithmic. This is a case
where the Master Theorem does not apply — the subproblem size does not shrink
geometrically — and reaching for it would be a mistake.

---

## 10. Set cover (greedy)

The greedy loop's cost is bounded by the number of passes times the work per pass:

```
T(S, U) = (number of passes) × Θ(S · U)
```

Each pass adds at least one set to the cover (the selected set covers at least one
new element, otherwise every element is already covered and the loop ends), so the
number of passes is at most `min(S, U)`:

```
T(S, U) = O(S · U · min(S, U))
```

### The ratio recurrence

The approximation guarantee is itself proved by a recurrence over uncovered
elements. Let `OPT` be the optimal cost and `U_t` the uncovered count before step
`t`. Greedy's cost satisfies:

```
cost(greedy) ≤ Σ_t (cost of step t)
and each step's cost ≤ OPT · (|U_t| − |U_{t+1}|) / |U_t|
```

Summing the per-element charges across the `|U_t|` values telescopes into the
harmonic series:

```
cost(greedy) ≤ OPT · Σ_{i=1}^{U} 1/i = OPT · H(U)
```

so greedy is an `H(U) = ln U + O(1)` approximation.

### DocuTrace's instance

`S = 8` rules, so the exhaustive variant costs `2^8 · U = 256·U` — polynomial at
this size. The exact optimum is therefore computable, and greedy's actual ratio can
be *measured* rather than bounded. See `NP_COMPLETENESS.md` §5.

---

## 11. The pipeline as a whole

The pipeline's cost is a **sum over stages**, not a recurrence, because the stages
are sequential (the DAG's width is 1 at the critical path):

```
T_pipeline(N, W, C, K, D, S) =
      Θ(V + E)          scheduling
    + Θ(N)              validation
    + Θ(N)              extraction
    + Θ(N)              normalisation
    + Θ(W)              candidate retrieval per indexed document
    + Θ(K · N)          field detection (K KMP searches over N characters)
    + Θ(K · V_f · E_f)  field validation (matching)
    + Θ(N)              hashing
    + Θ(C)              duplicate lookup
    + Θ(C · D²)         similarity analysis      ← dominant
    + Θ(S log S)        structural validation
    + Θ(2^R · U)        decision
    + Θ(N)              reporting
```

### Identifying the dominant term

For a typical document (`N ≈ 10⁴` characters, `C ≈ 10²` candidates,
`D = 2000`, `K ≈ 11`, `S ≈ 6`, `R = 8`):

| Term | Approximate magnitude |
| --- | --- |
| `V + E` | 32 |
| `N` terms (×4) | 4 × 10⁴ |
| `K · N` | 1.1 × 10⁵ |
| `K · V_f · E_f` | ~10³ |
| `C` | 10² |
| **`C · D²`** | **4 × 10⁸** |
| `S log S` | ~15 |
| `2^R · U` | ~10³ |

The DP term dominates by four orders of magnitude. That is not a coincidence; it is
the reason `DP_MAX_TOKENS` exists as a configurable cap. Capping `D` is the single
highest-leverage performance decision in the system, and the code reports when the
cap was hit rather than silently truncating.

### Reducing the dominant term

The `C` factor is addressed by staged candidate retrieval (hash filters first,
token-overlap second), which reduces the number of documents reaching the DP from
"all of them" to a small candidate set. A factor-`C` reduction at the dominant term
is worth more than optimising any other stage, which is why retrieval is a
separate, measured stage.

---

## 12. Summary table

| Algorithm | Recurrence | Method | Solution |
| --- | --- | --- | --- |
| Merge sort | `T(n) = 2T(n/2) + Θ(n)` | Master (case 2) + substitution | `Θ(n log n)` |
| Quick sort (balanced) | `T(n) = 2T(n/2) + Θ(n)` | Master (case 2) | `Θ(n log n)` |
| Quick sort (worst) | `T(n) = T(n−1) + Θ(n)` | Unrolling | `Θ(n²)` |
| Binary search | `T(n) = T(n/2) + Θ(1)` | Master (case 2) + unrolling | `Θ(log n)` |
| Inversion counting | `T(n) = 2T(n/2) + Θ(n)` | Master (case 2) | `Θ(n log n)` |
| LCS (naive recursion) | `T(n,m) = T(n−1,m) + T(n,m−1)` | Lattice-path counting | `Θ(2^(n+m)/√(n+m))` |
| LCS (tabulated) | — | Direct cell count | `Θ(nm)` |
| Edit distance (naive) | `T(n,m) = 3-way branch` | Branching bound | `Ω(3^min(n,m))` |
| Edit distance (tabulated) | — | Direct cell count | `Θ(nm)` |
| Huffman (heap) | — | Heap operation count | `Θ(n log n)` |
| Huffman (linear scan) | — | Merge count × scan cost | `Θ(n²)` |
| Bipartite matching | — | Augmentation count × BFS | `O(V·E)` |
| Set cover (greedy) | — | Pass count × pass cost | `O(S·U·min(S,U))`, ratio `H(U)` |
| Pipeline | Sum over stages | Term dominance | `Θ(C·D²)` dominant |

---

## 13. What the recurrences changed

Three decisions in DocuTrace were made *because* of the recurrence analysis, not
despite it:

1. **Tabulate, do not recurse.** The LCS and edit-distance recurrences are
   exponential when implemented literally. Writing them as recursion with the same
   formula — which looks correct and passes small tests — gives a system that dies
   on real documents. The table is not an optimisation; it is the difference
   between working and not working.

2. **Host inversion counting inside merge sort.** The merge sort recurrence already
   pays for the comparisons that detect inversions, so counting them adds `Θ(1)`
   per step rather than requiring a second `Θ(n²)` pass.

3. **Cap the DP.** The pipeline's dominant term is `C · D²`. Recognising this
   identifies the one parameter worth bounding, and explains why it is exposed as
   configuration with explicit truncation reporting rather than left unbounded.
