/**
 * Algorithm input helpers.
 *
 * The backend declares each parameter with a type (`json`, `text`, `boolean`,
 * `number`) and, for most of them, no default. Previously every `json` field
 * was pre-filled with `"[]"`, so opening the lab and pressing Run sent empty
 * arrays and the backend correctly rejected the request — five of the fourteen
 * algorithms failed on the very first click.
 *
 * These helpers replace that with a real, runnable example per parameter, so
 * every algorithm produces a meaningful result out of the box.
 */

import type { AlgorithmInfo, AlgorithmParameter } from "./types";

/** Worked examples for the required JSON parameters, keyed by algorithm. */
const JSON_EXAMPLES: Record<string, Record<string, unknown>> = {
  merge_sort: { items: [42, 7, 19, 3, 88, 15, 23] },
  quick_sort: { items: [42, 7, 19, 3, 88, 15, 23] },
  binary_search: { items: [3, 7, 15, 19, 23, 42, 88], target: "23" },
  inversions: { items: [42, 7, 19, 3, 88, 15, 23] },
  topological_sort: {
    nodes: ["upload", "extract", "verify", "compare", "report"],
    edges: [
      ["upload", "extract"],
      ["extract", "verify"],
      ["verify", "compare"],
      ["compare", "report"],
    ],
  },
  tree_traversal: {
    tree: [
      { name: "HEADER", level: 1 },
      { name: "HOLDER_DETAILS", level: 1 },
      { name: "ISSUING_AUTHORITY", level: 1 },
      { name: "DECLARATIONS", level: 1 },
      { name: "FOOTER", level: 1 },
    ],
    required_sections: ["HEADER", "DECLARATIONS", "FOOTER"],
  },
  bipartite_matching: {
    expected_fields: ["holder_name", "registration_number", "date_of_issue", "status"],
    extracted_fields: ["Holder Name", "Registration Number", "Date of Issue", "Status"],
  },
  set_cover: {
    requirements: ["holder_name", "registration_number", "date_of_issue", "status"],
    rules: [
      { name: "identity", cost: 1, covers: ["holder_name", "registration_number"] },
      { name: "dates", cost: 1, covers: ["date_of_issue"] },
      { name: "lifecycle", cost: 1, covers: ["status"] },
    ],
  },
};

/** Worked examples for text parameters, keyed by algorithm then parameter. */
const TEXT_EXAMPLES: Record<string, Record<string, string>> = {
  kmp: {
    text: "CERTIFICATE OF REGISTRATION\nHolder Name: Ananya R. Deshmukh\nRegistration Number: MH/2024/008421",
    pattern: "Ananya R. Deshmukh",
  },
  rabin_karp: {
    text: "CERTIFICATE OF REGISTRATION\nHolder Name: Ananya R. Deshmukh\nRegistration Number: MH/2024/008421",
    pattern: "MH/2024/008421",
  },
  sha256: {
    text: "CERTIFICATE OF REGISTRATION\nHolder Name: Ananya R. Deshmukh",
  },
  lcs: {
    source_text: "Holder Name: Ananya R. Deshmukh",
    target_text: "Holder Name: Ananya R. Deshmuk",
  },
  edit_distance: {
    source_text: "CERTIFICATE OF REGISTRATION",
    target_text: "CERTIFICAT OF REGISTRATION",
  },
  huffman: {
    text: "document verification and similarity detection",
  },
};

/** The raw text form shown in the input for one parameter. */
function exampleFor(algorithm: AlgorithmInfo, param: AlgorithmParameter): string {
  const byAlgo = JSON_EXAMPLES[algorithm.name] ?? {};
  const textByAlgo = TEXT_EXAMPLES[algorithm.name] ?? {};

  // An explicit backend default always wins.
  if (param.default !== undefined && param.default !== null) {
    return typeof param.default === "object"
      ? JSON.stringify(param.default, null, 2)
      : String(param.default);
  }

  if (param.type === "json") {
    const example = byAlgo[param.name];
    // A targeted example first, then a type-appropriate generic fallback so a
    // newly added backend parameter is still runnable.
    if (example !== undefined) return JSON.stringify(example, null, 2);
    if (param.name === "edges") return JSON.stringify([["a", "b"]], null, 2);
    if (param.name === "tree") return JSON.stringify([{ name: "HEADER", level: 1 }], null, 2);
    if (param.name === "nodes") return JSON.stringify(["a", "b"], null, 2);
    if (param.name.endsWith("_fields")) return JSON.stringify(["field_a"], null, 2);
    if (param.name === "rules") {
      return JSON.stringify([{ name: "rule", cost: 1, covers: ["field_a"] }], null, 2);
    }
    return JSON.stringify([1, 2, 3], null, 2);
  }

  if (param.type === "text") {
    const example = textByAlgo[param.name];
    if (example !== undefined) return example;
    return "sample text";
  }

  if (param.type === "boolean") return "false";
  if (param.type === "number") return "0";
  return "";
}

/** Build the initial string-valued form state for an algorithm. */
export function defaultInputs(algorithm: AlgorithmInfo): Record<string, string> {
  const out: Record<string, string> = {};
  for (const param of algorithm.parameters) {
    out[param.name] = exampleFor(algorithm, param);
  }
  return out;
}

export interface CoerceResult {
  payload?: Record<string, unknown>;
  error?: string;
}

/** Convert the string form state into the typed payload the backend expects. */
export function coerceInputs(
  algorithm: AlgorithmInfo,
  inputs: Record<string, string>
): CoerceResult {
  const payload: Record<string, unknown> = {};

  for (const param of algorithm.parameters) {
    const raw = inputs[param.name] ?? "";

    if (param.type === "json") {
      if (!raw.trim()) {
        payload[param.name] = [];
        continue;
      }
      try {
        payload[param.name] = JSON.parse(raw);
      } catch {
        return { error: `"${param.label}" is not valid JSON.` };
      }
    } else if (param.type === "boolean") {
      payload[param.name] = raw === "true";
    } else if (param.type === "number") {
      const value = Number(raw);
      if (raw.trim() && Number.isNaN(value)) {
        return { error: `"${param.label}" must be a number.` };
      }
      payload[param.name] = value || 0;
    } else {
      // `text` and anything unknown are sent through untouched; the backend
      // coerces further where it can (e.g. numeric search targets).
      payload[param.name] = raw;
    }
  }

  return { payload };
}
