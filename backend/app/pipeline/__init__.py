"""Upload orchestration pipeline.

The pipeline is where the DAA units are actually used:

* **Unit I (graphs)** — ``topological_sort(verification_pipeline_dag())`` decides
  the execution order of the stages, and the chosen order is recorded in the
  run's metadata.
* **Unit II (divide & conquer)** — ``merge_sort`` ranks similarity candidates by
  score and ``count_inversions`` quantifies section reordering between two
  documents.
* **Unit III (dynamic programming)** — ``lcs_dp`` / ``edit_distance`` power the
  detailed comparison stage (bounded by ``DP_MAX_TOKENS``).
* **Unit IV (greedy)** — ``huffman_encode`` produces archival statistics for the
  extracted text.
* **Unit V (network flow)** — ``bipartite_match`` aligns extracted labels with
  expected template fields.
* **Unit VI (NP-hardness)** — ``greedy_set_cover`` is available as an
  experiment; it never influences a verification outcome.
* **String algorithms** — ``kmp_search`` finds field labels,
  ``rabin_karp_search`` verifies template fragments, ``sha256_file`` /
  ``sha256_text`` fingerprint the file and its normalized text.

Stages are executed in topological order from the DAG (not a hard-coded
sequence), each stage is timed, and every algorithm call is recorded in
``algorithm_runs`` so the report can show real measurements.
"""

from app.pipeline.processing import (
    PipelineResult,
    process_document,
    recheck_document,
)

__all__ = ["process_document", "recheck_document", "PipelineResult"]
