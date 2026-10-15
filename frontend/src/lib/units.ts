/**
 * The VIT Pune DAA syllabus mapping.
 *
 * Each unit lists the syllabus topics, the DocuTrace component that implements
 * them, the genuine document-verification problem they solve, and the measured
 * complexity of the implementation that actually ships.
 */

export interface UnitTopic {
  topic: string;
  where: string;
}

export interface UnitComplexity {
  name: string;
  time: string;
  space: string;
}

export interface UnitMeta {
  roman: string;
  title: string;
  hours: string;
  summary: string;
  match: string[];
  topics: UnitTopic[];
  rationale: string[];
  complexities: UnitComplexity[];
}

export const UNITS: Record<string, UnitMeta> = {
  "1": {
    roman: "Unit I",
    title: "Foundations — Graphs and Complexity",
    hours: "Graphs & asymptotic analysis",
    summary:
      "The verification pipeline is a directed acyclic graph, so its stage order is derived by topological sort rather than hard-coded. The section hierarchy is traversed with DFS and BFS, and the health dashboard reports the asymptotic cost of every algorithm.",
    match: ["Unit I", "String"],
    topics: [
      { topic: "Asymptotic notation (Big-O, Θ, Ω)", where: "Performance dashboard, ALGORITHM_COMPLEXITY.md" },
      { topic: "Graph representations (adjacency list)", where: "topological_sort.py, tree_traversal.py" },
      { topic: "Topological sorting (Kahn's algorithm)", where: "verification_pipeline_dag() → pipeline order" },
      { topic: "Breadth-first and depth-first traversal", where: "Tree / section traversal in structure.py" },
      { topic: "Cycle detection in a dependency graph", where: "CycleError raised by topological_sort" },
    ],
    rationale: [
      "Hard-coding the pipeline stage order would silently break whenever a new stage is introduced. Deriving the order from the DAG means adding an edge is enough to reorder execution correctly.",
      "Kahn's algorithm also detects dependency cycles: if the pipeline ever became circular, the run fails loudly at the scheduling stage instead of producing a wrong result.",
      "DFS and BFS inspect the document's section tree: BFS finds missing top-level sections level by level, while DFS exposes nesting problems.",
    ],
    complexities: [
      { name: "Topological sort (Kahn)", time: "O(V + E)", space: "O(V + E)" },
      { name: "DFS / BFS traversal", time: "O(V + E)", space: "O(V)" },
      { name: "Cycle detection", time: "O(V + E)", space: "O(V)" },
    ],
  },
  "2": {
    roman: "Unit II",
    title: "Divide and Conquer",
    hours: "Sorting, searching, inversions",
    summary:
      "Merge sort ranks similarity candidates and counts section inversions; quick sort is included with an honest worst-case demonstration; binary search locates documents in sorted metadata.",
    match: ["Unit II"],
    topics: [
      { topic: "Merge sort (stable, Θ(n log n))", where: "merge_sort.py — candidate ranking" },
      { topic: "Quick sort (Lomuto partition)", where: "quick_sort.py — worst-case benchmark" },
      { topic: "Recurrence solving (Master Theorem)", where: "RECURRENCE_RELATIONS.md" },
      { topic: "Counting inversions", where: "inversions.py — section-reorder quantification" },
      { topic: "Binary search", where: "binary_search.py — sorted metadata lookup" },
    ],
    rationale: [
      "Duplicate candidates must be presented best-first; merge sort is stable, so candidates with equal scores keep their discovery order and the ranking is reproducible.",
      "Counting inversions turns 'the sections were reordered' into a single number: the minimum number of adjacent swaps needed to restore the original order.",
      "Quick sort is included precisely so the benchmark can show the O(n²) degenerate case on already-sorted input, rather than only its average behaviour.",
    ],
    complexities: [
      { name: "Merge sort", time: "Θ(n log n)", space: "O(n)" },
      { name: "Quick sort", time: "Θ(n log n) avg · O(n²) worst", space: "O(log n)" },
      { name: "Inversion counting", time: "Θ(n log n)", space: "O(n)" },
      { name: "Binary search", time: "O(log n)", space: "O(1)" },
    ],
  },
  "3": {
    roman: "Unit III",
    title: "Dynamic Programming",
    hours: "Sequence comparison",
    summary:
      "The core comparison engine. Longest Common Subsequence measures shared content; Levenshtein edit distance measures how many edits separate two versions and reconstructs the optimal edit script.",
    match: ["Unit III", "String", "Hashing"],
    topics: [
      { topic: "Longest Common Subsequence", where: "lcs.py — token-level shared content" },
      { topic: "Levenshtein edit distance", where: "edit_distance.py — field-level change detection" },
      { topic: "Optimal substructure & overlapping subproblems", where: "DYNAMIC_PROGRAMMING.md" },
      { topic: "Space-optimised DP (rolling rows)", where: "lcs_length_optimized, edit_distance_optimized" },
      { topic: "Pattern matching (KMP, Rabin-Karp)", where: "kmp.py, rabin_karp.py — label search" },
    ],
    rationale: [
      "Two documents can share a template yet be different records. LCS distinguishes 'the same content' from 'the same layout'.",
      "Edit distance is what lets the system say a registration number changed by one character rather than claiming the whole document is unrelated.",
      "The DP is bounded by the dp_max_tokens setting so a hostile mega-document cannot force a quadratic blow-up.",
    ],
    complexities: [
      { name: "LCS (full DP)", time: "O(nm)", space: "O(nm)" },
      { name: "LCS (length only)", time: "O(nm)", space: "O(min(n,m))" },
      { name: "Edit distance", time: "O(nm)", space: "O(nm) · O(min) optimised" },
      { name: "KMP", time: "O(n + m)", space: "O(m)" },
      { name: "Rabin-Karp", time: "O(n + m) expected", space: "O(1)" },
    ],
  },
  "4": {
    roman: "Unit IV",
    title: "Greedy Algorithms",
    hours: "Huffman coding",
    summary:
      "Huffman coding builds an optimal prefix-free code by repeatedly merging the two least-frequent symbols. In DocuTrace it produces archival compression statistics for extracted text, with honest accounting that includes the codebook.",
    match: ["Unit IV"],
    topics: [
      { topic: "Greedy choice property", where: "huffman.py — always merge the two rarest symbols" },
      { topic: "Huffman coding", where: "huffman_encode() — prefix code construction" },
      { topic: "Priority queue / heap usage", where: "heapq-based merge loop" },
      { topic: "Optimality argument (exchange argument)", where: "GREEDY_ANALYSIS.md" },
      { topic: "Prefix-free decoding", where: "round-trip verification of every encoding" },
    ],
    rationale: [
      "Archival storage of extracted text is a real cost, and Huffman coding is the canonical demonstration that a locally optimal greedy choice yields a globally optimal code.",
      "The implementation reports the true compressed size including the serialised codebook, so a small document is honestly reported as growing rather than as a magical win.",
      "Every encoding is decoded back and compared, so a claimed compression ratio is never reported for a code that cannot be reversed.",
    ],
    complexities: [
      { name: "Huffman coding", time: "O(n log n)", space: "O(n)" },
      { name: "Decoding", time: "O(n)", space: "O(n)" },
    ],
  },
  "5": {
    roman: "Unit V",
    title: "Network Flow & Matching",
    hours: "Bipartite matching, max flow",
    summary:
      "Aligning expected template fields with the fields actually extracted is a bipartite matching problem. It is reduced to maximum flow and solved with Edmonds-Karp, so one extracted field can never satisfy two expected fields.",
    match: ["Unit V"],
    topics: [
      { topic: "Bipartite graphs", where: "bipartite_matching.py — expected vs extracted fields" },
      { topic: "Maximum bipartite matching", where: "bipartite_match() via flow reduction" },
      { topic: "Edmonds-Karp (BFS augmenting paths)", where: "max-flow solver on the flow network" },
      { topic: "Flow network construction", where: "source → expected → extracted → sink" },
      { topic: "Compatibility edges from aliases", where: "exact label, approved alias, label similarity" },
    ],
    rationale: [
      "A naive one-to-one loop over fields mis-assigns when a document contains an unexpected extra label; a matching formulation guarantees a consistent global assignment.",
      "Edmonds-Karp's BFS guarantee gives a predictable bound, which matters because field alignment runs on every upload.",
      "The flow construction makes the compatibility rules explicit and testable rather than buried in nested conditionals.",
    ],
    complexities: [
      { name: "Max bipartite matching (Edmonds-Karp)", time: "O(V · E²)", space: "O(V + E)" },
      { name: "Here, with L expected and R extracted", time: "O(L · R · (L + R))", space: "O(L + R)" },
    ],
  },
  "6": {
    roman: "Unit VI",
    title: "NP-Completeness (optional)",
    hours: "Intractability",
    summary:
      "Choosing the cheapest set of verification rules that still covers every requirement is weighted Set Cover, which is NP-hard. This unit compares a polynomial greedy approximation against the exhaustive optimum on small instances. It is an academic experiment and never affects a real verification outcome.",
    match: ["Unit VI"],
    topics: [
      { topic: "Polynomial-time reductions", where: "Set Cover → decision problem discussion" },
      { topic: "Set Cover (NP-hard)", where: "set_cover.py" },
      { topic: "Greedy approximation (ln n ratio)", where: "greedy_set_cover()" },
      { topic: "Exhaustive search & exponential growth", where: "solve_set_cover_exhaustive()" },
      { topic: "P vs NP reasoning", where: "NP_COMPLETENESS.md" },
    ],
    rationale: [
      "Real systems do pick a minimal rule set, and it matters that the honest answer is 'this is NP-hard, so we approximate'.",
      "Comparing greedy against the exhaustive optimum on small instances makes the approximation ratio concrete instead of theoretical.",
      "The experiment is quarantined from the verification path by design: it is a lab tool, and the decision engine never consults it.",
    ],
    complexities: [
      { name: "Greedy set cover", time: "O(T · n · m)", space: "O(n + m)" },
      { name: "Exhaustive set cover", time: "O(2ⁿ · n · m)", space: "O(n)" },
    ],
  },
};

export function getUnit(unit: string): UnitMeta | null {
  return UNITS[unit] ?? null;
}
