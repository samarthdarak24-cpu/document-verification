# NP-Completeness and the Limits of DocuTrace

**DocuTrace — Intelligent Document Verification & Similarity Detection System**

Every algorithmic system has a place where the problems stop being tractable and
the engineering has to change. In DocuTrace that place is **set cover**, and
knowing exactly where it sits is what keeps the system honest: the pipeline runs an
approximation *because the exact problem is NP-hard*, and it says so.

This document establishes the hardness, states what it forces DocuTrace to do, and
— just as importantly — distinguishes the parts of the system that are *not* hard,
because misdiagnosing a polynomial problem as NP-hard is its own failure mode.

---

## 1. The complexity classes, precisely enough to use

| Class | Definition used here |
| --- | --- |
| **P** | Decision problems solvable in polynomial time in the input size. |
| **NP** | Decision problems for which a *yes* instance has a certificate verifiable in polynomial time. Equivalently, solvable by a nondeterministic Turing machine in polynomial time. |
| **NP-hard** | `L` is NP-hard if every `L' ∈ NP` polynomial-time reduces to `L` (`L' ≤_p L`). |
| **NP-complete** | `L ∈ NP` and `L` is NP-hard. |
| **co-NP** | The complements of NP problems: *no* instances have polynomial certificates. |

Two facts do all the work below:

**Fact 1 (reduction transfers hardness).** If `L' ≤_p L` and `L'` is NP-hard, then
`L` is NP-hard. Reducing *from* a known-hard problem *to* the new one shows the new
one is at least as hard.

**Fact 2 (closure under composition).** `≤_p` is transitive. Chains of reductions
accumulate hardness.

Two conventions this document respects, because sloppiness here is the most common
student error:

- **Decision problems, not optimisation problems.** "Is there a cover of size ≤ k?"
  is in NP. "Find the minimum cover" is NP-hard but not in NP (it is a function
  problem). When proving membership we always phrase the decision version.
- **Reductions go in one direction.** `Vertex Cover ≤_p Set Cover` proves Set Cover
  is NP-hard. It says nothing about Vertex Cover being NP-hard — that is the known
  starting point, not a conclusion.

---

## 2. What in DocuTrace is genuinely hard

**Set Cover (decision version).**

> Given a finite universe `U`, a family `S = {S₁, …, S_m}` of subsets of `U`, and an
> integer `k`, does there exist a subfamily `S' ⊆ S` with `|S'| ≤ k` and
> `⋃_{S ∈ S'} S = U`?

**Theorem NPC1.** Set Cover is NP-complete.

*Membership.* Given a candidate `S'`, verify `|S'| ≤ k` (count, linear) and
`⋃ S' = U` (mark each element of each chosen set; check all of `U` marked,
`O(Σ|S_i ∩ U|)`). Both polynomial. So Set Cover ∈ NP. ∎

*Hardness.* By reduction from **Vertex Cover** (Karp, 1972).

---

## 3. Reduction: Vertex Cover → Set Cover

**Vertex Cover (decision).** Given a graph `G = (V, E)` and integer `k`, is there
`V' ⊆ V` with `|V'| ≤ k` such that every edge has at least one endpoint in `V'`?

Vertex Cover is NP-complete (reduction from 3-SAT; Karp's original list). We reduce
it to Set Cover.

**Construction.** Given `G = (V, E)` with `|E| = m`, build the Set Cover instance:

```
U = E                                       universe is the edge set
For each vertex v ∈ V:  S_v = { e ∈ E : v ∈ e }      v covers its incident edges
k unchanged
```

The family is `S = { S_v : v ∈ V }`, so there is one set per vertex, and `S_v` is
the set of edges incident to `v`. This construction is `O(|V| + |E|)` — polynomial,
in fact linear.

**Lemma NPC2.** `G` has a vertex cover of size ≤ `k` iff `(U, S)` has a set cover of
size ≤ `k`.

*Proof.*

(⇒) Let `V'` be a vertex cover of `G`, `|V'| ≤ k`. Every edge `e = {u, w}` has `u ∈
V'` or `w ∈ V'` (or both). Hence `e ∈ S_u` or `e ∈ S_w` for some chosen vertex, so
`e ∈ ⋃_{v ∈ V'} S_v`. Every edge is covered, so `{S_v : v ∈ V'}` covers `U` and has
size `|V'| ≤ k`.

(⇐) Let `{S_v : v ∈ V'}` cover `U` with `|V'| ≤ k`. Take any edge `e ∈ E = U`.
Since the family covers `U`, `e ∈ S_v` for some `v ∈ V'`, which by construction
means `v` is incident to `e` — i.e. `v` is an endpoint of `e`. Every edge has an
endpoint in `V'`, so `V'` is a vertex cover of size ≤ `k`. ∎

**Theorem NPC3.** Set Cover is NP-hard, hence NP-complete (with Theorem NPC1).

*Proof.* Lemma NPC2 exhibits a polynomial-time mapping that preserves the answer in
both directions, so `Vertex Cover ≤_p Set Cover`. Vertex Cover is NP-hard, so by
Fact 1, Set Cover is NP-hard. With membership from Theorem NPC1, Set Cover is
NP-complete. ∎

Note the direction: hardness flows **from** Vertex Cover (**to** Set Cover. The
construction is also a *bijection-preserving* reduction — solutions correspond
exactly, not merely in existence — which is what makes the "iff" in Lemma NPC2
clean.

---

## 4. What this forces DocuTrace to do

DocuTrace's rule-selection problem (§3.1 of `GREEDY_ANALYSIS.md`) is a **weighted**
Set Cover: minimise `Σ c(r)` subject to covering `U`. The decision version of
weighted Set Cover is NP-complete by the same reduction (take all `c(r) = 1`, then
"cost ≤ k" is "size ≤ k"), so the weighted problem is NP-hard too, and the
optimisation problem has no known polynomial algorithm.

There are exactly four honest responses, and DocuTrace uses three of them.

### Response 1 — Approximate, with a proven ratio

Use the greedy density heuristic, whose `H(U)`-bound is proven in
`GREEDY_ANALYSIS.md` §3.4 and implemented in `app/algorithms/set_cover.py`. Cost
`O(|R|²|U|)`. Guarantee `≤ H(U)·OPT`. This is what the **live pipeline** runs.

### Response 2 — Solve exactly, but only on bounded instances

Enumerate all `2^{|R|}` subsets. With the current `|R| = 8` that is 256 subsets;
with `|R| = 12` it is 4,096. Both are instant. This is used in the **DAA
Laboratory**, and only there, for two reasons:

1. It gives the *ground truth* against which the greedy's ratio is measured — the
   laboratory reports "greedy found cost 3, optimum is 2, ratio 1.50" rather than
   only the bound. Measured ratio beats asserted bound.
2. It lets a student *see* the approximation gap on a real instance rather than
   taking the theory on faith.

### Response 3 — Change the question

Two variants of Set Cover are polynomial and DocuTrace exploits one:

| Variant | Complexity | Why |
| --- | --- | --- |
| Cover where every element is in exactly 2 sets | **P** (reduces to 2-SAT / matching) | structure constrains the problem |
| Cover where the universe is an interval and sets are intervals | **P** (greedy is exact) | greedy-choice property holds |
| Cover with **bounded set count** `\|R\| ≤ c` | `O(2^c · \|U\|)` | polynomial for each fixed `c` |

The third row is the honest description of Response 2: `2^c` is polynomial *for
each fixed `c`*, which is exactly why the bound must be enforced by configuration.
This is a statement about fixed-parameter tractability, not a claim that Set Cover
became easy.

### Response 4 — Accept the ceiling, and document it

The `|R|` ceiling is a **hard configuration limit** in `app/core/config.py`
(`MAX_RULES_FOR_EXHAUSTIVE`). Exceeding it does not silently degrade; the API
returns the greedy result with `solver: "greedy"` and `exhaustive_skipped: true`,
and the Laboratory shows a banner. A system that quietly used the approximation
while claiming optimality would be lying about its own guarantees — the exact
failure this document exists to prevent.

---

## 5. What in DocuTrace is *not* hard (and must not be called hard)

This is the more common error: treating a polynomial problem as intractable and
paying a cost that was never required.

| Problem in DocuTrace | Status | Why it is not hard |
| --- | --- | --- |
| String matching (KMP, Rabin–Karp) | **P**, `O(n + m)` | deterministic linear scan; no search over solutions |
| LCS / edit distance | **P**, `Θ(nm)` | DP over `(n+1)(m+1)` states |
| Sorting / inversion counting | **P**, `Θ(n log n)` | comparison sorting bound |
| Topological sort | **P**, `Θ(V + E)` | Kahn's algorithm |
| Binary search | **P**, `Θ(log n)` | monotone predicate |
| Huffman coding | **P**, `Θ(n log n)` | greedy-choice property holds (§2.4 of `GREEDY_ANALYSIS.md`) |
| **Bipartite matching** | **P**, `O(V·E²)` | **not** NP-hard — see below |
| Duplicate detection (as implemented) | **P** | staged hashing + bounded similarity |
| Set cover (exact) | **NP-hard** | the one genuinely hard component |

**Bipartite matching deserves the emphasis**, because it is the natural place to
expect hardness and there is none. Maximum bipartite matching is in P —
Edmonds–Karp gives `O(V·E²)` and Hopcroft–Karp gives `O(E√V)`. The hardness results
for matching concern **general** graphs (finding a matching of bounded size, or
maximum matching with general-graph techniques needing blossom contraction with
correctness subtleties) and *3-dimensional* matching, which **is** NP-complete.

DocuTrace's field corroboration is 2-dimensional and bipartite. It is in P, it is
solved exactly, and `NETWORK_FLOW.md` proves the flow formulation correct. **No
approximation is used or needed there.** It would be a real engineering error to
"approximate the matching" on the false belief that it is hard — the exact answer
is available in microseconds.

**The practical distinction.** Hardness is a property of the *problem*, not of the
input size. DocuTrace's matching instances are small *and* polynomial; its set-cover
instances are also small *but* exponential in the worst case, so the latter is the
one that needs a ceiling and a stated guarantee. Confusing "small instance" with
"easy problem" is exactly how a system ends up with an unbounded `2^n` in
production.

---

## 6. Reductions DocuTrace deliberately does *not* need

For completeness, the natural neighbours of the problems DocuTrace does solve, and
why the hard ones never arise:

| Hard problem | Would arise if… | DocuTrace's avoidance |
| --- | --- | --- |
| **Set Cover** | rule selection minimised exactly | approximation + bounded exact (`§4`) |
| **3-Dimensional Matching** | matching *three* field lists simultaneously | matching is bipartite, two-sided (`NETWORK_FLOW.md`) |
| **Longest Common Subsequence for `k > 2` sequences** | comparing many documents pairwise | comparisons are always pairwise; `k = 2` is DP (`DYNAMIC_PROGRAMMING.md`) |
| **Multiple Sequence Alignment** | aligning > 2 token streams at once | not done; pairwise only |
| **Subset Sum / Bin Packing** | packing reports into a size-limited store | no such constraint; reports stream to disk |
| **Maximum Clique** | finding a largest mutually-similar document cluster | duplicate *groups* are unions of pairwise equal/near-equal relations, not cliques |
| **Graph Colouring** | scheduling rule execution under a `k`-engine limit | execution is serial and ordered by the pipeline DAG |

Several of these are one small requirement away from entering the system. The
reason to enumerate them is that each is a **design constraint**: if a future change
introduces "compare three documents at once" or "pack reports to a fixed byte
budget", the complexity class of the system changes, and that must be an explicit
decision rather than an accident.

---

## 7. The approximation ratio, measured rather than asserted

The theoretical bound from `GREEDY_ANALYSIS.md` §3.4 is `H(U)`. The Laboratory
computes the **actual** ratio on each instance:

```
ratio = cost(greedy) / cost(exhaustive optimum)
```

and reports it alongside the bound. This matters because `H(U)` is a *worst-case*
guarantee: on typical instances the true ratio is far smaller. Reporting only the
bound would overstate the error; reporting only the measured ratio would hide the
worst case. DocuTrace reports both, and the test suite pins the adversarial
instance (`test_greedy_suboptimal_instance`, greedy 3 vs optimum 2) so the worst
case is never lost from view.

| Bound | Value at `\|U\| = 16` | Nature |
| --- | --- | --- |
| `H(U)` (proven) | 3.381 | worst case, achievable |
| `ln\|U\| + 1` (weaker) | 3.773 | convenient upper bound on `H` |
| Measured on Lab instances | typically 1.0–1.5 | instance-specific |

---

## 8. Summary

| Question | Answer |
| --- | --- |
| Is DocuTrace's set-cover stage NP-hard? | **Yes** (Vertex Cover ≤_p Set Cover, Theorem NPC3) |
| Does the pipeline solve it exactly? | **No** — greedy `H(U)`-approximation |
| Is the approximation honest? | **Yes** — ratio reported, worst case pinned by a test, ceiling enforced |
| Is bipartite matching NP-hard? | **No** — in P; solved exactly with Edmonds–Karp |
| Are the string / DP / sort stages hard? | **No** — all in P with matching measured complexity |
| Where does hardness enter? | Exactly one place: exact weighted set cover |

The value of this analysis is not that it proves something difficult. It is that it
delimits precisely where the system *cannot* promise optimality, and ensures the
one place where it cannot is (a) bounded, (b) approximate with a proven ratio, and
(c) labelled as such in both the API response and the user interface.

---

*See also:* `GREEDY_ANALYSIS.md` §3 (the greedy solver and its `H(U)` bound),
`NETWORK_FLOW.md` §3 (integrality and why matching stays in P),
`CORRECTNESS_PROOFS.md` §13 (set-cover optimality proof and charging argument),
`ALGORITHM_COMPLEXITY.md` (aggregate pipeline complexity including the `2^R·U`
term), `BENCHMARK_RESULTS.md` §5 (measured matching cost).
