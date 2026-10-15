# Dynamic Programming in DocuTrace

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

Two algorithms in DocuTrace are dynamic programs: the longest common subsequence
and the Levenshtein edit distance. Both are O(nm) recurrences; both have naive
recursive formulations that are exponential; and both are used in the live
duplicate-detection path, not in a demonstration.

This document covers the formulations, why DP is the right paradigm for each, the
space optimisations and what they cost, and the two places where the DP genuinely
determines whether a duplicate is caught.

---

## 1. Why dynamic programming at all

Two properties must both hold for DP to apply.

**Optimal substructure.** An optimal solution to the whole problem contains optimal
solutions to subproblems. Without it, you cannot build the answer from sub-answers.

**Overlapping subproblems.** The naive recursion revisits the same subproblem many
times. Without overlap, divide-and-conquer (which never revisits) is the right
tool and DP buys nothing.

LCS and edit distance satisfy both:

| Property | LCS | Edit distance |
| --- | --- | --- |
| Optimal substructure | Yes — Theorem 10 in `CORRECTNESS_PROOFS.md` | Yes — Theorem 11 |
| Overlapping subproblems | Yes — `(i,j)` reached from `(i−1,j)` and `(i,j−1)` | Yes — `(i,j)` reached from three predecessors |

The overlap is what makes the recursion exponential and the tabulation polynomial.
For LCS the naive recursion is `Θ(2^(n+m)/√(n+m))`; for edit distance it is worse,
`Ω(3^min(n,m))`. Tabulating visits each of the `(n+1)(m+1)` states exactly once.

**The concrete consequence.** Two documents of 1,000 characters each have
10⁶ DP cells. The naive LCS recursion would make on the order of `C(2000,1000) ≈
10^600` calls. The tabulated version makes 10⁶. There is no constant-factor
tuning that closes that gap; the paradigm is the difference.

---

## 2. Longest Common Subsequence

### 2.1 The problem

Given sequences A and B, find the longest sequence that appears as a subsequence of
both, preserving order but not requiring contiguity.

For DocuTrace, A and B are **word tokens**, not characters. `"the registration
number changed"` versus `"the registration no changed"` shares the subsequence
`[the, registration, changed]` — a length-3 match against a 4-token input, which
correctly reports "mostly the same document with one field relabelled". Character
level would report a much smaller similarity and lose the structure.

### 2.2 Formulation

Let `A` have `n` tokens and `B` have `m`. Define the subproblem:

> `L[i][j]` = the length of the LCS of the first `i` tokens of A and the first `j`
> tokens of B.

Recurrence:

```
L[i][0] = 0                                     for 0 ≤ i ≤ n
L[0][j] = 0                                     for 0 ≤ j ≤ m
L[i][j] = L[i-1][j-1] + 1                       if A[i-1] == B[j-1]
L[i][j] = max(L[i-1][j], L[i][j-1])             otherwise
```

The answer is `L[n][m]`.

**Why the recurrence is right.** If the last tokens match, they can both be part of
an LCS: take the LCS of the prefixes and append the match. If they differ, no LCS
uses both, so it uses neither the last token of A nor the last token of B — hence
it is an LCS of one of the two shorter prefix pairs, and the longer one wins. Full
proof in `CORRECTNESS_PROOFS.md` §10.

### 2.3 Table construction

Fill row by row, left to right. Each cell reads three neighbours, all already
computed:

```
        j-1   j
  i-1  [ ↖ ] [ ↑ ]
  i    [ ← ] [ X ]      X is computed from ↖, ↑, ←
```

```python
for i in range(1, n + 1):
    for j in range(1, m + 1):
        if a[i - 1] == b[j - 1]:
            table[i][j] = table[i - 1][j - 1] + 1
        else:
            table[i][j] = max(table[i - 1][j], table[i][j - 1])
```

Time `Θ(nm)`, space `Θ(nm)`.

### 2.4 The worked example

`A = [the, quick, brown, fox, jumps]`, `B = [the, slow, brown, fox, leaps]`

```
      ""   the  slow  brown  fox  leaps
 ""    0    0     0     0     0     0
 the   0    1     1     1     1     1
 quick 0    1     1     1     1     1
 brown 0    1     1     2     2     2
 fox   0    1     1     2     3     3
 jumps 0    1     1     2     3     3
```

`L[5][5] = 3`, the subsequence `[the, brown, fox]`.

### 2.5 Reconstructing the alignment

The length alone is not enough for DocuTrace's diff view — the *spans* must be
highlighted. Walk backwards from `L[n][m]`:

```
i, j = n, m
while i > 0 and j > 0:
    if A[i-1] == B[j-1]:
        record "match", i -= 1, j -= 1
    elif L[i-1][j] >= L[i][j-1]:
        record "delete from A", i -= 1
    else:
        record "insert into B", j -= 1
while i > 0: record "delete from A", i -= 1
while j > 0: record "insert into B", j -= 1
```

Ties (`L[i-1][j] == L[i][j-1]`) are broken consistently in favour of deleting from
A, which makes the alignment deterministic — the same pair of documents always
produces the same diff, so the rendered diff is reproducible across runs.

Reconstruction costs `Θ(n + m)`, negligible against the `Θ(nm)` table.

**The dependency that forces the full table.** Backtracking reads `L[i-1][j-1]`,
`L[i-1][j]`, and `L[i][j-1]` for cells it has already left behind. Two rows are not
enough. This is the trade-off in §2.6.

### 2.6 Space optimisation

**Observation.** The forward pass reads only the previous row and the current row.
So the *length* can be computed in `Θ(min(n, m))` space:

```python
prev = [0] * (m + 1)
for i in range(1, n + 1):
    curr = [0] * (m + 1)
    for j in range(1, m + 1):
        if a[i-1] == b[j-1]:
            curr[j] = prev[j-1] + 1
        else:
            curr[j] = max(prev[j], curr[j-1])
    prev = curr
return prev[m]
```

Iterate so that the shorter sequence indexes the row: `min(n, m)` cells per row
instead of `max(n, m)`.

| Variant | Time | Space | Alignment recoverable |
| --- | --- | --- | --- |
| Full table | `Θ(nm)` | `Θ(nm)` | Yes |
| Two rows | `Θ(nm)` | `Θ(min(n, m))` | No |

At n = m = 1,000: 1,000,000 cells versus 2,000 — a 500× reduction, paid for by
losing the alignment.

**Which one DocuTrace uses.** The length-only variant during candidate screening,
where many document pairs are compared and only the score is needed. The full
table when the user opens the diff view and asks to see the matched spans. This is
the same algorithm called two ways, chosen per call site by what the caller needs
— not a global setting.

### 2.7 Hirschberg's algorithm — considered and not used

Hirschberg's divide-and-conquer construction achieves `Θ(nm)` time and
`Θ(min(n, m))` space *with* alignment recovery, by recursively splitting: compute
the forward LCS lengths from the start and the backward LCS lengths from the end,
find the split point where the two halves sum to the optimum, and recurse.

DocuTrace does not implement it. The reasoning:

- The full table is `Θ(nm)` cells, bounded by `DP_MAX_TOKENS²`. At the default cap
  of 2,000 tokens that is at most 4 × 10⁶ integers — a few tens of megabytes.
  Bounded and acceptable for a workstation application.
- Hirschberg adds a log-factor in practice (the recursion re-does table work) and
  materially more code for a space saving the cap already bounds.
- The cap makes the worst case *known*, which is worth more than a smaller unknown
  worst case.

Recording *why* a well-known optimisation was declined is part of the design. The
constraint that makes it unnecessary (`D` is capped) is explicit and configurable.

### 2.8 Where LCS decides an outcome

**Sample `03_certificate_modified_reg.pdf`.** The registration number changes from
`MH/2024/008421` to `MH/2024/008422` — one digit. SHA-256 differs, so it is not an
exact duplicate. The normalized-text hash differs, so it is not a content
duplicate by hash.

Word-level LCS then measures the overlap. One token out of roughly twenty differs,
so the LCS covers nearly everything and the reported similarity is high. That is
how the system distinguishes "the same document with a typo" from "a different
document" — and why the answer is `CONTENT_DUPLICATE` at 0.9723 rather than
`unique`.

**Sample `06_certificate_alt_labels.pdf`.** The same content with different field
labels (`Registration Number` → `Registration No.`). Word-level LCS sees a
substantial shared subsequence, so the score stays high enough for a
`NEAR_DUPLICATE_CANDIDATE` verdict rather than a fresh-document verdict.

### 2.9 LCS complexity in DocuTrace's pipeline

The pipeline calls LCS up to `C` times, once per candidate. Each call is `Θ(D²)`
with `D = DP_MAX_TOKENS`. So LCS contributes `Θ(C·D²)` — the dominant term in the
whole pipeline (see `ALGORITHM_COMPLEXITY.md` §8). Lowering `D` reduces cost
quadratically; the trade-off is that documents longer than the cap are compared on
a prefix, which the response reports via `truncated` and `truncation_note`.

---

## 3. Edit distance (Levenshtein)

### 3.1 The problem

The minimum number of single-character insertions, deletions, and substitutions
required to turn A into B.

### 3.2 Formulation

> `D[i][j]` = the minimum edit distance between the first `i` characters of A and
> the first `j` characters of B.

```
D[i][0] = i
D[0][j] = j
D[i][j] = D[i-1][j-1]                                if A[i-1] == B[j-1]
D[i][j] = 1 + min( D[i-1][j],      # delete A[i-1]
                   D[i][j-1],      # insert B[j-1]
                   D[i-1][j-1] )   # substitute
```

The three predecessors correspond to the three ways the final character of B can be
produced. Full proof in `CORRECTNESS_PROOFS.md` §11.

### 3.3 The worked example

`kitten` → `sitting`:

```
        ""   s   i   t   t   i   n   g
 ""      0   1   2   3   4   5   6   7
 k       1   1   2   3   4   5   6   7
 i       2   2   1   2   3   4   5   6
 t       3   3   2   1   2   3   4   5
 t       4   4   3   2   1   2   3   4
 e       5   5   4   3   2   2   3   4
 n       6   6   5   4   3   3   2   3
```

`D[6][7] = 3`: substitute `k → s`, substitute `e → i`, insert `g`.

### 3.4 Recovering the operations

DocuTrace returns the actual operations, not only the count. Walk backwards from
`D[n][m]`:

```
while i > 0 or j > 0:
    if i > 0 and j > 0 and A[i-1] == B[j-1] and D[i][j] == D[i-1][j-1]:
        record "match"; i -= 1; j -= 1
    elif i > 0 and j > 0 and D[i][j] == D[i-1][j-1] + 1:
        record ("substitute", A[i-1], B[j-1]); i -= 1; j -= 1
    elif i > 0 and D[i][j] == D[i-1][j] + 1:
        record ("delete", A[i-1]); i -= 1
    else:
        record ("insert", B[j-1]); j -= 1
```

Ordering of the branches matters: match is checked before substitution so that an
equal character is never reported as a needless substitution, and substitution is
checked before deletion/insertion so the cheaper explanation is preferred. This
makes the operation list minimal and deterministic.

### 3.5 Space optimisation

Same two-row argument as LCS, since `D[i][j]` reads only `D[i-1][·]` and
`D[i][j-1]`:

| Variant | Time | Space | Operations recoverable |
| --- | --- | --- | --- |
| Full table | `Θ(nm)` | `Θ(nm)` | Yes |
| Two rows | `Θ(nm)` | `Θ(min(n, m))` | No |

`with_operations=True` selects the full table; the default length-only path uses
two rows and is what runs in high-volume field comparison, where thousands of field
pair values are compared during validation.

### 3.6 Where edit distance decides an outcome

**Field drift detection.** During field comparison, every extracted field value in
A is compared with its counterpart in B. Edit distance with operations tells the
reviewer exactly what changed:

```
registration_number:  "MH/2024/008421"  →  "MH/2024/008422"
                      distance 1, substitution at offset 12: '1' → '2'
```

That is the finding the UI renders. A bare similarity score would say "0.97
similar"; the operation list says *which character changed*. For a verification
tool, the second is the actionable output.

**Field-diff ranking.** `POST /api/compare/field-diff` computes edit distance for
every shared field, then sorts by similarity ascending so the most-changed fields
appear first. Merge sort (stable, `Θ(k log k)`) is used for the ranking; the
edit-distance table is the data being ranked. Two DAA techniques in one endpoint,
each doing what it is suited to.

**Why not use LCS for fields too.** LCS measures shared content; edit distance
measures change. For a field value that must match exactly, "how many edits away"
is the right question, and distance 0 is the pass condition. LCS length 3 out of 4
would not distinguish a valid field from a corrupted one nearly as sharply.

### 3.7 Edit distance as a metric

The function behaves as a metric on strings (with a small caveat), which DocuTrace
relies on:

- **Identity.** `D(A, A) = 0`.
- **Symmetry.** `D(A, B) = D(B, A)`. Each operation has an inverse of equal cost
  (insert ↔ delete, substitute ↔ substitute), and the recurrence is symmetric.
- **Triangle inequality.** `D(A, C) ≤ D(A, B) + D(B, C)` — transforming A to C via B
  is a valid (possibly suboptimal) path, so the direct optimum cannot exceed it.

All three are asserted in the test suite.

**The caveat.** When substitution cost is 1, `D` is a true metric; when
substitution cost is set to 2 (equivalent to delete + insert), it becomes the LCS
distance `n + m − 2·LCS`. DocuTrace uses cost 1, so it is a metric. This matters
because metric properties are what let the distance be compared meaningfully across
document pairs of different lengths.

---

## 4. DP versus the alternatives

| Approach | Time | Space | Correct for these problems? |
| --- | --- | --- | --- |
| Naive recursion | Exponential | Exponential (stack) | Yes, but infeasible |
| Memoised recursion | `Θ(nm)` | `Θ(nm)` + call overhead | Yes |
| **Tabulation (used)** | `Θ(nm)` | `Θ(nm)` or `Θ(min(n,m))` | Yes |
| Greedy matching | `Θ(n + m)` | `Θ(1)` | **No** — see below |
| Hash-only comparison | `Θ(n)` | `Θ(1)` | Only detects exact equality |

**Why not greedy.** A greedy LCS — walk both sequences taking the first matching
pair at each step — is not correct. On `A = "AB"`, `B = "BA"`, greedy matches `A`
first and reports length 1; the true LCS is also length 1 here, but the *alignment*
is arbitrary and the algorithm fails on larger inputs. A clean counterexample:
`A = "ABCBDAB"`, `B = "BDCABA"` — greedy gives 3, DP gives 4 (`BCBA` or `BDAB`).
Reported similarity would be wrong by 33% on a small input, worse on large ones.

**Why DP is not optional here.** The overlap structure means the subproblems are
not independent, so divide-and-conquer cannot be applied directly. A greedy choice
does not have an exchange argument. The two paradigms that could apply (greedy,
divide-and-conquer) both fail, leaving DP.

---

## 5. Implementation notes

### 5.1 Tokenisation for LCS

`lcs.py` operates on a token list supplied by the caller, not on a raw string. The
caller (`similarity.py`) tokenises with the *same* normaliser used elsewhere in the
pipeline, so two documents that normalise to the same tokens are compared on the
same basis. Doing the tokenisation in the algorithm would duplicate the normaliser
and risk divergence; doing it inside the algorithm would also break purity.

### 5.2 The trace

Both DP algorithms can emit a step trace, but a cell-by-cell trace of an n × m
table is useless for a human — a 1,000 × 1,000 table gives 10⁶ steps. The trace is
therefore capped (500 steps) and, for the Laboratory, records only the
structurally interesting events: row transitions, matches, and the reconstruction
walk. The UI player then shows a readable sequence rather than a firehose.

### 5.3 Truncation reporting

When the token count exceeds `DP_MAX_TOKENS`, the comparison runs on a prefix. The
response carries:

```json
{
  "truncated": true,
  "truncation_note": "Comparison used the first 2000 of 4317 tokens.",
  "compared_source_tokens": 2000,
  "source_tokens": 4317
}
```

Reporting this is a correctness requirement, not politeness. A similarity score
computed on a prefix is a *different measurement* from one computed on the whole
document, and presenting it as the latter would be a silent falsehood. The
`compared_*_tokens` and `*_tokens` fields let a caller detect and react to the
difference.

### 5.4 Purity

Both modules are pure: given the same tokens they return the same result, with no
database, filesystem, or global state. That is what makes them exhaustively
testable (brute-force oracles, randomised cross-checks) and what keeps a pipeline
bug from being misdiagnosed as an algorithm bug.

---

## 6. Correctness enforcement

The proofs in `CORRECTNESS_PROOFS.md` are backed by tests that would fail if each
proof's key step were violated.

| Claim | Test |
| --- | --- |
| LCS length is optimal | Brute-force enumeration of all subsequences of the shorter input; compared exactly |
| LCS recurrence is right | Randomised cross-check against the brute-force oracle |
| Alignment is valid | Reconstructed alignment asserted to be a common subsequence of exactly the reported length |
| Two-row variant is equivalent | Length-only and full-table variants asserted equal on randomised inputs |
| Edit distance is optimal | Memoised brute-force oracle over all edit sequences |
| Edit distance is symmetric | `D(A,B) == D(B,A)` on random pairs |
| Triangle inequality | `D(A,C) ≤ D(A,B) + D(B,C)` on random triples |
| Operations reconstruct the string | Applying the returned operations to A is asserted to yield B, and the operation count to equal the distance |
| Known values | `kitten → sitting = 3`; `LCS("ABCBDAB","BDCABA") = 4` |

The brute-force oracles are deliberately simple and obviously correct — a
double loop and an exhaustive search — so that a mismatch points at the DP, not at
the test.

---

## 7. Dynamic programming beyond LCS and edit distance

Two further places in DocuTrace use overlapping-subproblem reasoning even though
they are not classic table-filling DPs.

**The pipeline's DAG schedule.** Topological sort is not DP, but it is the same
underlying idea: a total order derived from a dependency structure, computed once
and reused. The pipeline memoises the computed order for the life of the process
rather than recomputing it per upload.

**Candidate screening as a staged filter.** Retrieval runs cheaper tests first
(hash equality, then token-set overlap) and only then the expensive DP. This is
the "spend the cheap resource first" principle that DP's own subproblem ordering
embodies — the same instinct applied one level up.

---

## 8. Summary

| Aspect | LCS | Edit distance |
| --- | --- | --- |
| Subproblem | `L[i][j]` = LCS length of prefixes | `D[i][j]` = min edits between prefixes |
| Recurrence shape | Two-way max, or +1 on match | Three-way min, or +0 on match |
| Time | `Θ(nm)` | `Θ(nm)` |
| Space (full) | `Θ(nm)` | `Θ(nm)` |
| Space (optimised) | `Θ(min(n, m))` | `Θ(min(n, m))` |
| Naive recursion | `Θ(2^(n+m)/√(n+m))` | `Ω(3^min(n,m))` |
| Reconstruction | Alignment (match/delete/insert) | Operations (match/sub/delete/insert) |
| Used for | Similarity score, matched spans | Field drift, exact field comparison |
| DocuTrace file | `app/algorithms/lcs.py` | `app/algorithms/edit_distance.py` |
| Token unit | Words | Characters (field values) |

Both are bounded by `DP_MAX_TOKENS`, both report truncation explicitly, and both
are cross-checked against a brute-force oracle on randomised inputs. The DP is not
a demonstration of the technique; it is the mechanism by which DocuTrace decides
whether two documents are the same document.
