import { useMemo, useState } from "react";
import { Play, RotateCcw, Sigma, Timer } from "lucide-react";
import { Button, Card, CardBody, CardHeader, ErrorState, StatusBadge } from "./ui";
import { useRunAlgorithm } from "../hooks/queries";
import { coerceInputs, defaultInputs } from "../lib/algorithmInputs";
import type { AlgorithmInfo } from "../lib/types";
import { cn, formatMs } from "../lib/utils";

/**
 * A tabbed playground for the algorithms belonging to one DAA unit.
 *
 * Each tab shows the algorithm's parameters as a small form. Values are coerced
 * from their text representation to the type the backend expects (JSON, boolean
 * or number) before the request is sent.
 */
export default function UnitRunner({ algorithms }: { algorithms: AlgorithmInfo[] }) {
  const [activeName, setActiveName] = useState(algorithms[0]?.name ?? "");
  const active = algorithms.find((a) => a.name === activeName) ?? algorithms[0];

  if (!active) return null;

  return (
    <Card>
      <CardHeader
        icon={<Sigma />}
        title={active.title}
        subtitle={active.unit}
        actions={<StatusBadge tone="blue">{active.complexity_time}</StatusBadge>}
      />

      <div className="flex flex-wrap gap-1.5 border-b border-line px-4 py-3">
        {algorithms.map((algo) => (
          <button
            key={algo.name}
            type="button"
            onClick={() => setActiveName(algo.name)}
            className={cn(
              "rounded-control border px-2.5 py-1 text-[12px] transition-colors duration-fast",
              active.name === algo.name
                ? "border-brand bg-brand text-txt-inverse"
                : "border-line bg-canvas text-txt-muted hover:border-line-strong hover:text-txt"
            )}
          >
            {algo.title}
          </button>
        ))}
      </div>

      <RunnerForm key={active.name} algorithm={active} />
    </Card>
  );
}

function RunnerForm({ algorithm }: { algorithm: AlgorithmInfo }) {
  const defaults = useMemo(() => defaultInputs(algorithm), [algorithm]);

  const [inputs, setInputs] = useState<Record<string, string>>(defaults);
  const [error, setError] = useState<string | null>(null);
  const run = useRunAlgorithm();

  const elapsed = useMemo(() => {
    const summary = run.data?.result_summary as Record<string, unknown> | undefined;
    const value = summary?.elapsed_ms ?? run.data?.elapsed_ms;
    return typeof value === "number" ? value : null;
  }, [run.data]);

  function submit() {
    const { payload, error: coerceError } = coerceInputs(algorithm, inputs);
    if (coerceError || !payload) {
      setError(coerceError ?? "Invalid input.");
      return;
    }
    setError(null);
    run.mutate({ algorithm: algorithm.name, inputs: payload });
  }

  return (
    <CardBody className="space-y-5">
      <p className="text-[13px] leading-relaxed text-txt-muted">{algorithm.description}</p>

      <div className="space-y-4">
        {algorithm.parameters.map((param) => (
          <label key={param.name} className="block max-w-lg">
            <span className="dt-label">
              {param.label}
              {param.required ? <span className="ml-1 text-pill-rose-txt">*</span> : null}
            </span>
            {param.type === "json" ? (
              <textarea
                className="dt-input mt-1 font-mono text-[12px]"
                rows={4}
                value={inputs[param.name] ?? ""}
                onChange={(e) => setInputs((s) => ({ ...s, [param.name]: e.target.value }))}
              />
            ) : param.type === "boolean" ? (
              <select
                className="dt-select mt-1"
                value={inputs[param.name] ?? "false"}
                onChange={(e) => setInputs((s) => ({ ...s, [param.name]: e.target.value }))}
              >
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            ) : (
              <input
                className="dt-input mt-1"
                value={inputs[param.name] ?? ""}
                onChange={(e) => setInputs((s) => ({ ...s, [param.name]: e.target.value }))}
              />
            )}
          </label>
        ))}
      </div>

      <div className="flex items-center gap-2.5">
        <Button variant="primary" icon={<Play />} disabled={run.isPending} onClick={submit}>
          {run.isPending ? "Running…" : "Run"}
        </Button>
        <Button
          variant="secondary"
          icon={<RotateCcw />}
          onClick={() => {
            setInputs(defaults);
            run.reset();
            setError(null);
          }}
        >
          Reset
        </Button>
        {elapsed !== null ? (
          <span className="dt-mono ml-auto inline-flex items-center gap-1.5 text-[12px] text-txt-faint">
            <Timer className="h-3.5 w-3.5" />
            measured {formatMs(elapsed)}
          </span>
        ) : null}
      </div>

      {error ? <ErrorState error={error} /> : null}
      {run.isError ? <ErrorState error={run.error} /> : null}

      {run.data ? (
        <pre className="max-h-[440px] overflow-auto rounded-panel border border-line bg-canvas-section p-4 font-mono text-[11.5px] leading-relaxed text-txt-muted">
          {JSON.stringify(run.data, null, 2)}
        </pre>
      ) : null}
    </CardBody>
  );
}
