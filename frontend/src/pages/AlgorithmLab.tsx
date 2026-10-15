import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { FlaskConical, ListFilter, Play, RotateCcw, SquareSigma } from "lucide-react";
import {
  Card,
  CardBody,
  CardHeader,
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useAlgorithms, useAlgorithmHistory, useRunAlgorithm } from "../hooks/queries";
import { coerceInputs, defaultInputs } from "../lib/algorithmInputs";
import type { AlgorithmInfo } from "../lib/types";
import { cn, formatInt, formatMs, humanize } from "../lib/utils";

const UNIT_ORDER = [
  "Unit I",
  "Unit II",
  "Unit III",
  "Unit IV",
  "Unit V",
  "Unit VI",
  "String",
  "Hashing",
];

export default function AlgorithmLab() {
  const algorithms = useAlgorithms();
  const history = useAlgorithmHistory({ limit: 25 });
  const [selected, setSelected] = useState<AlgorithmInfo | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, AlgorithmInfo[]>();
    for (const algo of algorithms.data ?? []) {
      const unit = algo.unit ?? "Other";
      const bucket = UNIT_ORDER.find((u) => unit.startsWith(u)) ?? "Other";
      if (!map.has(bucket)) map.set(bucket, []);
      map.get(bucket)!.push(algo);
    }
    return [...map.entries()].sort(
      (a, b) => UNIT_ORDER.indexOf(a[0]) - UNIT_ORDER.indexOf(b[0])
    );
  }, [algorithms.data]);

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="DAA Laboratory"
        title="Algorithm laboratory"
        description="Every algorithm below is implemented from scratch and runs live in the backend. Choose one, supply inputs, and read the real result — including the operation count and the measured execution time."
        actions={
          <Link to="/performance" className="dt-btn-secondary">
            Performance analysis
          </Link>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(240px,300px)_1fr]">
        <Card className="lg:sticky lg:top-6 lg:self-start">
          <CardHeader
            icon={<ListFilter />}
            title="Algorithms"
            subtitle={`${algorithms.data?.length ?? 0} available`}
          />
          {algorithms.isLoading ? (
            <Spinner label="Loading" />
          ) : algorithms.isError ? (
            <CardBody>
              <ErrorState error={algorithms.error} />
            </CardBody>
          ) : (
            <div className="max-h-[70vh] overflow-y-auto px-2.5 py-3">
              {grouped.map(([unit, items]) => (
                <div key={unit} className="mb-4">
                  <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-txt-faint">
                    {unit}
                  </p>
                  <ul className="space-y-0.5">
                    {items.map((algo) => (
                      <li key={algo.name}>
                        <button
                          type="button"
                          onClick={() => setSelected(algo)}
                          className={cn(
                            "w-full truncate rounded-control px-2.5 py-1.5 text-left text-[12.5px] font-medium transition-colors duration-fast",
                            selected?.name === algo.name
                              ? "bg-brand text-txt-inverse"
                              : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                          )}
                        >
                          {algo.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-6">
          {selected ? (
            <AlgorithmRunner key={selected.name} algorithm={selected} />
          ) : (
            <Card>
              <EmptyState
                icon={<FlaskConical />}
                title="Select an algorithm"
                description="Pick any algorithm from the list to open its playground."
              />
            </Card>
          )}

          <Card>
            <CardHeader
              icon={<SquareSigma />}
              title="Recent algorithm runs"
              subtitle="Recorded during real document processing and lab executions"
            />
            {history.isLoading ? (
              <Spinner label="Loading history" />
            ) : (history.data ?? []).length === 0 ? (
              <EmptyState title="No runs recorded yet" />
            ) : (
              <table className="dt-table">
                <thead>
                  <tr>
                    <th>Algorithm</th>
                    <th>Input</th>
                    <th className="text-right">Operations</th>
                    <th className="text-right">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {(history.data ?? []).map((row, i) => (
                    <tr key={i}>
                      <td className="font-medium text-txt">{humanize(row.algorithm)}</td>
                      <td
                        className="max-w-[300px] truncate text-[12px] text-txt-muted"
                        title={row.input_summary ?? ""}
                      >
                        {row.input_summary ?? "—"}
                      </td>
                      <td className="text-right tabular-nums">{formatInt(row.operation_count)}</td>
                      <td className="text-right tabular-nums">
                        {formatMs(row.execution_time_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function AlgorithmRunner({ algorithm }: { algorithm: AlgorithmInfo }) {
  const defaults = useMemo(() => defaultInputs(algorithm), [algorithm]);
  const [inputs, setInputs] = useState<Record<string, string>>(defaults);
  const [parseError, setParseError] = useState<string | null>(null);
  const run = useRunAlgorithm();

  return (
    <>
      <Card>
        <CardHeader
          icon={<FlaskConical />}
          title={algorithm.title}
          subtitle={algorithm.unit}
          actions={<StatusBadge tone="lavender">{algorithm.complexity_time}</StatusBadge>}
        />
        <CardBody className="space-y-5">
          <p className="text-[13px] leading-relaxed text-txt-muted">{algorithm.description}</p>

          <div className="flex flex-wrap gap-1.5">
            <StatusBadge tone="blue">Time {algorithm.complexity_time}</StatusBadge>
            <StatusBadge tone="slate">Space {algorithm.complexity_space}</StatusBadge>
          </div>

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
            <Button
              variant="primary"
              icon={<Play />}
              disabled={run.isPending}
              onClick={() => {
                const { payload, error } = coerceInputs(algorithm, inputs);
                if (error || !payload) {
                  setParseError(error ?? "Invalid input.");
                  return;
                }
                setParseError(null);
                run.mutate({ algorithm: algorithm.name, inputs: payload });
              }}
            >
              {run.isPending ? "Running…" : "Run algorithm"}
            </Button>
            <Button
              variant="secondary"
              icon={<RotateCcw />}
              onClick={() => {
                setInputs(defaults);
                run.reset();
                setParseError(null);
              }}
            >
              Reset inputs
            </Button>
          </div>

          {parseError ? <ErrorState error={parseError} /> : null}
          {run.isError ? <ErrorState error={run.error} /> : null}
        </CardBody>
      </Card>

      {run.data ? (
        <Card>
          <CardHeader
            icon={<SquareSigma />}
            title="Result"
            subtitle="Measured on the backend, right now"
          />
          <CardBody>
            <pre className="max-h-[520px] overflow-auto rounded-panel border border-line bg-canvas-section p-4 font-mono text-[12px] leading-relaxed text-txt-muted">
              {JSON.stringify(run.data, null, 2)}
            </pre>
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
