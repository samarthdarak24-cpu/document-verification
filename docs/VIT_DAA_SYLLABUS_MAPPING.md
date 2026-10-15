# VIT Pune DAA Syllabus Mapping

**Course:** Design and Analysis of Algorithms
**Programme:** B.Tech. Computer Engineering
**Academic Year:** 2026–27
**Project:** DocuTrace — Intelligent Document Verification & Similarity Detection System

---

## How to read this document

DocuTrace is not a collection of algorithm demonstrations bolted onto an
application. It is a document verification system whose *actual production
behaviour* is implemented by the algorithms on this course's syllabus. Every
algorithm listed below runs on real uploaded documents in the live pipeline —
none of them exist only inside a test.

For each unit this document records:

- **Syllabus topics** covered, quoted from the unit description
- **Algorithms implemented** in `backend/app/algorithms/`
- **Where the algorithm actually runs** in the DocuTrace pipeline
- **Why the algorithm is the right tool** for that job
- **Evidence** — the test file, the API surface, and the UI route that expose it

A mapping that could be satisfied by a toy example is not a mapping. Each entry
below names a file path where the algorithm is doing load-bearing work.

---

## Summary table

| Unit | Topic | Algorithms | Runs in production? |
| --- | --- | --- | --- |
| I | Foundations, analysis, trees, DAG scheduling | Topological sort (Kahn), BFS, DFS | Yes — pipeline scheduling; structure analysis |
| II | Divide and conquer, sorting, searching | Merge sort, quick sort, binary search, inversion counting | Yes — candidate ranking; threshold lookup; reorder scoring |
| III | Greedy and dynamic programming | LCS (word-level DP), edit distance, KMP, Rabin–Karp, SHA-256 | Yes — every duplicate decision depends on these |
| IV | Greedy algorithms, coding | Huffman coding | Yes — lossless archival with honest size accounting |
| V | Graph algorithms, flow | Bipartite matching via Edmonds–Karp | Yes — field-to-label assignment |
| VI | NP-completeness, approximation | Weighted set cover (greedy + exhaustive) | Yes — minimal rule set explaining a verdict |

---

## Unit I — Foundations of Algorithm Analysis; Trees and DAGs

### Syllabus topics covered

- Asymptotic notation (O, Ω, Θ) and their formal definitions
- Best / average / worst case analysis
- Recurrence relations and the Master Theorem
- Trees: terminology, representations, traversal
- **Directed acyclic graphs and topological ordering**

### Algorithms implemented

| Algorithm | File | Complexity |
| --- | --- | --- |
| Topological sort (Kahn's algorithm) | `app/algorithms/topological_sort.py` | O(V + E) |
| Breadth-first traversal | `app/algorithms/tree_traversal.py` | O(V + E) |
| Depth-first traversal (recursive and iterative) | `app/algorithms/tree_traversal.py` | O(V + E) |

### Where it runs in DocuTrace

**Topological sort schedules the verification pipeline.**

The document-processing pipeline is a genuine dependency graph, not a list. There
are thirteen stages, and they have real ordering constraints:

```
upload
  └─> file_validation
        └─> text_extraction
              └─> normalization
                    ├─> candidate_retrieval
                    │     └─> field_detection
                    │           └─> field_validation
                    ├─> hashing
                    │     └─> duplicate_lookup
                    │           └─> similarity_analysis
                    └────────────────────> structural_validation
                                              └─> verification_decision
                                                    └─> report_generation
```

`normalization` must precede both the field branch and the hashing branch, and
`duplicate_lookup` depends on `hashing` while `similarity_analysis` depends on
both `duplicate_lookup` and `candidate_retrieval`. Rather than hard-code the
order, the pipeline declares the edges and **computes** the execution order with
Kahn's algorithm.

This matters for three reasons:

1. The declared order is written into every run's `pipeline_order` field, so the
   execution order is auditable rather than implicit in the source.
2. Adding a stage is a matter of declaring its dependencies; the schedule adapts.
3. Cycle detection comes free — a cycle in the dependency graph is a programming
   error, and Kahn's algorithm reports it instead of deadlocking.

Kahn's algorithm is used rather than DFS-based topological sort because it also
gives a deterministic, layer-by-layer ordering (all in-degree-0 nodes at each
step are sorted), which makes the recorded order stable across runs. Stability
is a hard requirement: two runs over the same document must produce the same
`pipeline_order`, or the audit trail is worthless.

**Tree traversal walks the document structure.**

`analyze_structure()` builds a section tree from the extracted heading hierarchy
(a document with `Header > HolderDetails > Declarations` is a tree three levels
deep) and exposes both traversals:

- **BFS** yields the sections in document order, level by level — used to render
  the structure panel.
- **DFS** yields a depth-first linearisation used to detect a *skipped* level
  (a level-3 heading appearing before any level-2 heading) and to produce the
  ordered section list against which section reordering is scored in Unit II.

### Why this is not a toy

The pipeline DAG has thirteen nodes and nineteen edges and runs on every single
upload. The structure tree runs on every document whose extraction produced
headings. Neither is invoked only by a test.

### Evidence

- Implementation: `backend/app/algorithms/topological_sort.py`, `tree_traversal.py`
- Tests: `backend/tests/test_algorithms/test_topological_sort.py`, `test_tree_traversal.py`
- API: `POST /api/algorithms/run` with `algorithm: "topological_sort"` / `"tree_traversal"`
- Live use: `backend/app/pipeline/processing.py`, stage `scheduling`
- UI: `/lab/unit-1`
- Observable: every run's `pipeline_order` array, and the `scheduling` stage timing

---

## Unit II — Divide and Conquer; Sorting and Searching

### Syllabus topics covered

- Divide-and-conquer paradigm
- Merge sort and its recurrence T(n) = 2T(n/2) + Θ(n)
- Quick sort, partitioning, and its worst case
- Binary search and the loop invariant
- Comparison-based sorting lower bounds
- Counting inversions as a divide-and-conquer problem

### Algorithms implemented

| Algorithm | File | Complexity |
| --- | --- | --- |
| Merge sort (bottom-up, stable) | `app/algorithms/merge_sort.py` | Θ(n log n) |
| Quick sort (Lomuto partition, explicit stack) | `app/algorithms/quick_sort.py` | Θ(n log n) expected, O(n²) worst |
| Binary search (with pointer trace) | `app/algorithms/binary_search.py` | O(log n) |
| Inversion counting (modified merge sort) | `app/algorithms/inversions.py` | O(n log n) |

### Where it runs in DocuTrace

**Merge sort ranks similarity candidates — and it must be stable.**

When a document is uploaded, the system retrieves every previous document whose
token set overlaps enough to be worth comparing, then sorts the candidates by
score so the most promising are examined first (and so the reported "best
match" is well-defined).

Stability is not a nicety here, it is a correctness requirement. Two candidate
documents can have *identical* similarity scores — for example, two exact copies
of the same original. If the sort is unstable, which one is reported as "the"
match can differ between runs, and the audit trail becomes non-reproducible.
Merge sort guarantees that candidates with equal scores retain their input
order, so the tie is broken deterministically by candidate retrieval order,
which is itself deterministic (sorted by document ID).

An unstable O(n log n) sort — or a fast `sorted()` call whose stability we had
not verified — would silently violate this. Implementing merge sort ourselves
means the guarantee is in code we control.

**Quick sort orders analytics data in place.**

The analytics and benchmark views order records by score for display and for
percentile computation. Quick sort is used with an explicit stack (no recursion),
and the implementation deliberately uses a last-element pivot so that
already-sorted input degrades to O(n²). That degradation is *demonstrated* in
`/performance` rather than hidden — the benchmark dashboard shows the measured
quadratic curve next to the merge sort line, which is the whole point of the
comparison.

**Inversion counting quantifies section reordering.**

A document whose sections appear in a different order from the template is a
real verification concern: the content is intact, but the structure has been
altered. Rather than a boolean "reordered" flag, DocuTrace *measures* the
disorder.

The shared section names are ranked by their position in the reference document,
and the target document's ordering of those same sections is passed to the
inversion counter. The count of inversions is exactly the number of pairs that
appear in the wrong relative order, and it is normalised by the maximum possible
π = C(n,2) to give a reorder score in [0, 1].

```
sections in reference order:  [Header, Holder, Authority, Declarations, Footer]
target document order:        [Header, Holder, Declarations, Footer, Authority]
                              ranks:  0, 1, 3, 4, 2
inversions: (3,2), (4,2)  ->  2
max possible: C(5,2) = 10
reorder score: 2 / 10 = 0.20
```

This is why sample `05_certificate_reordered.pdf` is reported as
`INCONSISTENT_FIELDS` with a measured reorder score rather than being lumped in
with genuine content changes.

**Binary search looks up thresholds.**

The decision thresholds (at what similarity does a match become a
"near-duplicate" rather than a "content duplicate"?) are held in a sorted array
and located by binary search. The implementation exposes the `low`/`mid`/`high`
pointers at every step, which is what the Laboratory trace player steps through.

### Why divide and conquer, and where the recurrence bites

Both merge sort and inversion counting share the recurrence:

```
T(n) = 2·T(n/2) + Θ(n)
```

By the Master Theorem, a = 2, b = 2, f(n) = Θ(n), and log_b(a) = 1, so
f(n) = Θ(n^(log_b a)) — **case 2** — giving

```
T(n) = Θ(n log n)
```

The practical consequence in DocuTrace: candidate ranking and reorder scoring
scale to thousands of documents without becoming the bottleneck. Benchmarks
confirm this — see `BENCHMARK_RESULTS.md`, where merge sort goes from 0.537 ms at
n = 100 to 84.475 ms at n = 5,000. That is a 50× size increase for a 157× time
increase, against the ~86× that n log n predicts; the excess is dominated by
Python-level constant factors at small n, and the ratio converges as n grows.

### Evidence

- Implementation: `backend/app/algorithms/merge_sort.py`, `quick_sort.py`, `binary_search.py`, `inversions.py`
- Tests: `test_sorting.py`, `test_binary_search.py`, `test_inversions.py`
- Live use: `app/services/duplicate_detection.py` (candidate ranking),
  `app/api/routers/compare.py::_section_rank_reordering`
- UI: `/lab/unit-2`, `/performance`
- Observable: sample `05`'s reorder score; the merge-vs-quick curves in `/performance`

---

## Unit III — Dynamic Programming; String Algorithms

### Syllabus topics covered

- Dynamic programming: optimal substructure, overlapping subproblems
- Tabulation, the LCS recurrence, space optimisation
- Edit distance (Levenshtein) and its recurrence
- String matching: naive, KMP, Rabin–Karp
- Hashing and rolling hashes
- Cryptographic hashing (SHA-256) and its properties

### Algorithms implemented

| Algorithm | File | Complexity |
| --- | --- | --- |
| LCS (word-level, full DP + alignment) | `app/algorithms/lcs.py` | O(nm) time, O(nm) space; O(min(n,m)) length-only |
| Levenshtein edit distance (with operations) | `app/algorithms/edit_distance.py` | O(nm) time, O(min(n,m)) space |
| KMP with LPS table | `app/algorithms/kmp.py` | O(n + m) |
| Rabin–Karp with polynomial rolling hash | `app/algorithms/rabin_karp.py` | O(n + m) expected |
| SHA-256 (streaming, from scratch) | `app/algorithms/hashing.py` | O(n) |

### Where it runs in DocuTrace

This unit is the core of the product. Duplicate detection *is* these algorithms.

**KMP locates field labels.**

To extract `Registration Number: MH/2024/008421` from a wall of text, the system
must find the label. Labels vary (`Registration No.`, `Reg. Number`,
`Registration Number`), so finding them is a multi-pattern search. KMP is used
because it guarantees O(n + m) regardless of input — the classic adversarial case
(`text = "aaaaaa...a"`, `pattern = "aaab"`) that makes the naive search quadratic
is *common*, not exotic, in real documents: repeated field labels in a table
produce exactly this pattern. The LPS table means the text pointer never moves
backwards, so the search is linear no matter how repetitive the document is.

In the Certificate template, eleven field definitions each carry a set of
aliases, and each alias is located with KMP. That is the difference between
finding the registration number and finding an arbitrary number.

**Rabin–Karp searches many patterns at once.**

When screening a document for *all* known labels simultaneously, Rabin–Karp's
rolling hash lets each window's hash update in O(1) after the first, so the cost
per window is constant. The polynomial hash is computed over a fixed base modulo
a large prime; every hash match is then **verified character by character**, so a
collision can never produce a false positive. The two algorithms are deliberately
cross-checked against each other in the test suite — if they ever disagree on the
same input, one of them is wrong.

**SHA-256 is the first line of duplicate defence.**

Every upload is hashed with a streaming SHA-256 implementation. Two files with
the same hash are byte-identical, full stop — no similarity scoring needed. This
is the cheapest and most certain test, so it runs first:

- Sample `02_certificate_copy.pdf` is a byte-for-byte copy → identical SHA-256 →
  `EXACT_DUPLICATE`, similarity 1.0000, decided without any DP at all.

The implementation is streaming (64-byte block buffer, no need to hold the whole
file in memory) and is validated against the published NIST test vectors, so we
know it is real SHA-256 and not an approximation.

**LCS and edit distance decide the hard cases.**

When hashes differ, the documents are not identical — but they may still be the
same document with a change. That is the interesting case, and it is where DP
earns its place.

- **LCS** computes the longest common subsequence over *word* tokens. Words
  rather than characters, because "the registration number changed" is a
  meaningfully different observation from "one character changed". The full DP
  table is retained so the actual matched spans can be recovered and highlighted
  in the UI, not merely the length.
- **Edit distance** gives the character-level view and, crucially, the *list of
  operations* — where exactly the insertions, deletions and substitutions fell.
  That is what lets DocuTrace say "the registration number changed from
  `MH/2024/008421` to `MH/2024/008422`" instead of "0.97 similar".

Both are capped by `DP_MAX_TOKENS` because the recurrences are O(nm). This is an
honest engineering trade-off, and the API says so: when a comparison is
truncated, `truncated: true` and a `truncation_note` are returned rather than
silently comparing a prefix and reporting a misleading score.

### The recurrences

**LCS.** Let `L[i][j]` be the LCS length of `A[0..i)` and `B[0..j)`:

```
L[i][0] = 0,  L[0][j] = 0
L[i][j] = L[i-1][j-1] + 1                      if A[i-1] == B[j-1]
L[i][j] = max(L[i-1][j], L[i][j-1])            otherwise
```

Two properties make this DP valid: **optimal substructure** (the LCS of two
sequences is built from the LCS of their prefixes) and **overlapping
subproblems** (the same `(i, j)` is reached from both `(i-1, j)` and `(i, j-1)`).
Naive recursion is exponential; tabulation makes it O(nm).

**Edit distance.** Let `D[i][j]` be the minimum number of single-character edits
turning `A[0..i)` into `B[0..j)`:

```
D[i][0] = i,  D[0][j] = j
D[i][j] = D[i-1][j-1]                                        if A[i-1] == B[j-1]
D[i][j] = 1 + min(D[i-1][j], D[i][j-1], D[i-1][j-1])         otherwise
```

The three terms are delete, insert, substitute.

**Space optimisation.** Both tables are strictly "read the previous row and the
current row", so a full n×m table is needed only to *reconstruct* the alignment.
For the length-only queries used during candidate screening, DocuTrace keeps two
rows of `min(n, m)` and drops the space from O(nm) to O(min(n, m)). When the
alignment itself is wanted (for the diff view), the full table is retained.

At n = m = 1,000, that is the difference between a 1,000,000-cell table and two
1,000-cell rows.

### Evidence

- Implementation: `backend/app/algorithms/lcs.py`, `edit_distance.py`, `kmp.py`, `rabin_karp.py`, `hashing.py`
- Tests: `test_lcs.py`, `test_edit_distance.py`, `test_kmp.py`, `test_rabin_karp.py`, `test_hashing.py`
- Live use: `app/services/duplicate_detection.py`, `app/services/similarity.py`, `app/services/field_validation.py`
- UI: `/lab/unit-3`, `/compare` (the diff view is the LCS alignment rendered)
- Observable: sample `03` → 0.9723; sample `06` → 0.8974

---

## Unit IV — Greedy Algorithms

### Syllabus topics covered

- Greedy strategy and the greedy-choice property
- Optimal substructure in greedy contexts
- Huffman coding and variable-length codes
- Prefix-free codes and the coding tree
- When greedy fails — and how to tell

### Algorithms implemented

| Algorithm | File | Complexity |
| --- | --- | --- |
| Huffman coding (with tree metadata) | `app/algorithms/huffman.py` | O(n log n) |

### Where it runs in DocuTrace

**Huffman coding compresses extracted text for archival — with honest accounting.**

Every verification run stores the extracted text so the decision can be
re-examined later. Storing raw text for thousands of documents is wasteful;
Huffman is provably optimal among prefix-free codes, so there is no better
character-level scheme to reach for.

The honest part is this: DocuTrace reports the size **including the code table**.
A Huffman code achieves its compression by building a table specific to the input,
and that table must be stored alongside the payload to decode it. If the table costs
more than the savings, Huffman has made things worse — and for a short document
with a broad alphabet, that is exactly what happens.

So the implementation returns the compressed size, the uncompressed size, *and*
the code table size, and computes the net saving. `include_tree_metadata=True`
lets the caller ask for the tree so the Laboratory can draw it.

This is the point of the unit: Huffman is optimal *given the constraint that the
code must be prefix-free and the table is free*. Drop either assumption and the
conclusion changes. The code makes that visible instead of hiding it behind a
compression ratio.

**Constructing the code.** The algorithm repeatedly extracts the two
least-frequent symbols and merges them into a new node, using a binary heap so
each extraction costs O(log n). With n distinct symbols there are n − 1 merges,
giving O(n log n) total. The greedy choice is safe because of an exchange
argument: there exists an optimal prefix-free code in which the two least
frequent symbols are siblings at maximum depth, so merging them first loses
nothing.

### Evidence

- Implementation: `backend/app/algorithms/huffman.py`
- Tests: `test_huffman.py`
- API: `POST /api/algorithms/run` with `algorithm: "huffman"`, `include_tree_metadata: true`
- UI: `/lab/unit-4` (renders the code tree)
- Observable: the returned `compressed_size`, `table_size`, and `net_saving` fields

---

## Unit V — Graph Algorithms; Network Flow

### Syllabus topics covered

- Graph representations; bipartite graphs
- Maximum matching in bipartite graphs
- Augmenting paths
- Max-flow / min-cut and the Ford–Fulkerson method
- Edmonds–Karp (BFS-based augmenting paths)

### Algorithms implemented

| Algorithm | File | Complexity |
| --- | --- | --- |
| Bipartite maximum matching (Edmonds–Karp / Hopcroft–Karp style augmenting paths) | `app/algorithms/bipartite_matching.py` | O(V·E) |

### Where it runs in DocuTrace

**Field-to-label assignment is a matching problem.**

Extracted text contains field *labels*; a template declares field *definitions*
with several accepted aliases each. The question "which label belongs to which
field definition?" is not a lookup — it is an assignment problem, and it must
respect two hard constraints:

1. **One label maps to at most one field.** If `Date of Issue` matched both
   `issue_date` and `expiry_date`, the extraction is ambiguous and must be
   resolved, not silently double-assigned.
2. **A field definition is satisfied by at most one label.** Two different labels
   should not both claim to be the `registration_number`.

That is precisely a **bipartite matching**: labels on one side, field definitions
on the other, an edge where a label is an accepted alias of a definition. The
maximum matching assigns as many fields as possible without violating either
constraint.

**Why maximum matching rather than a greedy assignment.** A greedy pass — take
the first label that matches each field in turn — can produce a *smaller* matching
than the maximum, and therefore report a field as missing when a valid
assignment existed. A concrete failure: suppose labels `L1, L2` and definitions
`D1, D2`, with `L1` an alias of both `D1` and `D2`, and `L2` an alias only of
`D1`. Greedy that assigns `L1 → D1` first then leaves `D2` unmatched, reporting
`D2` as a missing required field and failing validation on a document that was
actually complete. The augmenting-path algorithm instead finds `L1 → D2,
L2 → D1`, and the document passes.

That is a false rejection caused purely by choosing the wrong algorithm. The
test suite includes exactly this configuration as a regression test.

**Where the flow enters.** Maximum bipartite matching is the integral special
case of max-flow: add a source connected to every label with capacity 1, a sink
connected from every definition with capacity 1, and run Edmonds–Karp using BFS
to find shortest augmenting paths. Because all capacities are integral, the
augmenting-path search produces an integral maximum flow, which is a maximum
matching. BFS (rather than DFS) is used because it bounds the number of
augmentations by the shortest-path lengths and gives the O(V·E) bound.

### Evidence

- Implementation: `backend/app/algorithms/bipartite_matching.py`
- Tests: `test_bipartite_matching.py`
- Live use: `app/services/field_validation.py`
- UI: `/lab/unit-5` (renders the bipartite graph and the augmenting path)
- Observable: which field definitions are satisfied on samples `01` and `06`

---

## Unit VI — NP-Completeness and Approximation

### Syllabus topics covered

- Decision vs optimisation problems
- Polynomial-time reductions
- NP, NP-hard, NP-complete; Cook–Levin
- Set cover and its NP-completeness
- Approximation algorithms and approximation ratios

### Algorithms implemented

| Algorithm | File | Complexity |
| --- | --- | --- |
| Weighted set cover — greedy (ln n)-approximation | `app/algorithms/set_cover.py` | O(S · U) per pass |
| Weighted set cover — exhaustive optimal | `app/algorithms/set_cover.py` | O(2^S) |

### Where it runs in DocuTrace

**Set cover selects the minimal set of rules that explains a verdict.**

When a document fails verification, several rules may fire:
`R003 missing required field`, `R005 similarity below threshold`,
`R007 section missing`. Many of these are *consequences* of one another. Reporting
all of them buries the cause under symptoms and is genuinely unhelpful to the
person reviewing the document.

What the reviewer wants is the **smallest set of findings that explains
everything observed**. Each rule, if it fires, implies a set of observable
symptoms:

| Rule | Explains |
| --- | --- |
| `R003` (missing required field) | required field absent, template compliance low |
| `R005` (similarity below threshold) | near-duplicate score, candidate match |
| `R007` (missing section) | expected section absent, structure mismatch |

Choosing the minimum-cost selection of rules whose combined symptoms cover every
observed symptom is **set cover**.

**Set cover is NP-complete.** The decision version — "is there a selection of at
most k sets covering the universe?" — is in NP (a selection can be verified in
polynomial time) and NP-hard by reduction from Vertex Cover. So no polynomial
algorithm is known, and none is expected to exist.

**What DocuTrace does about it.** Two strategies, both present in the codebase,
and the choice between them is itself the lesson:

- **Greedy** repeatedly takes the rule that covers the most still-uncovered
  symptoms, weighted by the rule's cost (severity). It runs in polynomial time
  and achieves an approximation ratio of `H(n) = ln n + O(1)`. This is the
  *production path* — it is what actually chooses the explanation shown to the
  user.
- **Exhaustive** enumerates all 2^S subsets and returns the true optimum. It is
  exponential and therefore bounded by a small rule count, which is fine here
  because DocuTrace has eight rules. It exists so the greedy result can be
  *validated*: the test suite asserts the greedy answer is never worse than the
  optimum on every rule set the engine can produce.

That pairing is the point. Because the real instance size is tiny (8 rules), the
optimal answer is computable, so the approximation can be checked against ground
truth rather than merely asserted to be close. The `ln n` bound is a guarantee
for arbitrary inputs; here we can do better — we can measure the actual gap, and
in every case DocuTrace can reach, greedy returns the optimum.

### Why this belongs in a document verifier

Nothing about document verification requires solving set cover in general. It
requires solving a *specific, tiny* instance optimally. Recognising that the
general problem is NP-complete is what tells you (a) not to look for a polynomial
exact algorithm, (b) to bound the instance so an exact algorithm remains
feasible, and (c) to keep a polynomial approximation available for the
exact path's guards. That reasoning is the actual deliverable of this unit.

### Evidence

- Implementation: `backend/app/algorithms/set_cover.py`
- Tests: `test_set_cover.py` (including greedy-vs-optimal assertions)
- UI: `/lab/unit-6` (runs both strategies side by side and shows the gap)
- Observable: the explanation string on any failed verification

---

## Unit-to-route map

| Unit | Laboratory route | Also observable at |
| --- | --- | --- |
| I | `/lab/unit-1` | Every run's `pipeline_order`; `/documents/:id` structure panel |
| II | `/lab/unit-2` | `/performance`; sample `05`'s reorder score |
| III | `/lab/unit-3` | `/compare` diff view; samples `02`, `03`, `04`, `06` |
| IV | `/lab/unit-4` | The Huffman panel on unit 4 |
| V | `/lab/unit-5` | `/documents/:id` field panel |
| VI | `/lab/unit-6` | The explanation on any failed verification |

---

## Algorithms implemented

Fourteen algorithms, all in `backend/app/algorithms/`, all implemented from
scratch — no `sort`, no `hashlib`, no `networkx`, no third-party algorithm
library is called for any of them.

```
app/algorithms/
├── topological_sort.py     Kahn's algorithm            O(V + E)
├── tree_traversal.py       BFS, DFS (rec + iter)       O(V + E)
├── merge_sort.py           Stable merge sort           Θ(n log n)
├── quick_sort.py           Lomuto, explicit stack      Θ(n log n) avg / O(n²) worst
├── binary_search.py        With pointer trace          O(log n)
├── inversions.py           Modified merge sort         O(n log n)
├── lcs.py                  Word-level DP + alignment   O(nm), O(min(n,m)) space
├── edit_distance.py        Levenshtein + operations    O(nm), O(min(n,m)) space
├── kmp.py                  LPS-table search            O(n + m)
├── rabin_karp.py           Polynomial rolling hash     O(n + m) expected
├── hashing.py              Streaming SHA-256           O(n)
├── huffman.py              Greedy optimal coding       O(n log n)
├── bipartite_matching.py   Edmonds–Karp augmenting     O(V · E)
└── set_cover.py            Greedy + exhaustive         O(S·U) / O(2^S)
```

Each module exposes a dataclass result carrying its measurements (`comparisons`,
`operations`, `elapsed_ns`, `peak_bytes`) and, where meaningful, a step trace for
the Laboratory player. Every one has a dedicated test file; the algorithms whose
output can be checked against a brute-force reference are checked against one on
randomised inputs.
