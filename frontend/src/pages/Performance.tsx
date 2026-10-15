import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Gauge, ListFilter, Timer, TrendingUp, Zap } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatTile,
  StatusBadge,
} from "../components/ui";
import { useBenchmarkOptions, useBenchmarks, useRunBenchmarks } from "../hooks/queries";
import type { BenchmarkRowOut } from "../lib/types";
import { cn, formatBytes, formatInt, formatMs, humanize } from "../lib/utils";

// Blue-forward palette that stays legible on white and matches the accent.
const PALETTE = ["#3B65D9", "#7C3AED", "#0EA5E9", "#22C55E", "#F59E0B", "#EC4899", "#14B8A6"];

const AXIS = "#A3A3A3";
const GRID = "rgba(23,23,23,0.07)";

export default function Performance() {
  const options = useBenchmarkOptions();
  const stored = useBenchmarks({ limit: 1000 });
  const run = useRunBenchmarks();

  const [selectedAlgorithms, setSelectedAlgorithms] = useState<string[]>([]);
  const [selectedSizes, setSelectedSizes] = useState<number[]>([]);
  const [repeats, setRepeats] = useState(3);
  const [liveRows, setLiveRows] = useState<BenchmarkRowOut[] | null>(null);
  const [metric, setMetric] = useState<"time" | "operations">("time");

  const rows = liveRows ?? stored.data ?? [];

  const byAlgorithm = useMemo(() => {
    const map = new Map<string, BenchmarkRowOut[]>();
    for (const row of rows) {
      if (!map.has(row.algorithm)) map.set(row.algorithm, []);
      map.get(row.algorithm)!.push(row);
    }
    return [...map.entries()];
  }, [rows]);

  const sizeSeries = useMemo(() => {
    // One data point per input size, one key per algorithm.
    const sizeSet = [...new Set(rows.map((r) => r.input_size))].sort((a, b) => a - b);
    const algorithms = [...new Set(rows.map((r) => r.algorithm))];
    return {
      algorithms,
      data: sizeSet.map((size) => {
        const point: Record<string, number | string> = { size };
        for (const algo of algorithms) {
          const matching = rows.filter((r) => r.algorithm === algo && r.input_size === size);
          if (matching.length > 0) {
            point[algo] =
              metric === "time"
                ? Number(
                    (
                      matching.reduce((s, r) => s + r.execution_time_ms, 0) / matching.length
                    ).toFixed(4)
                  )
                : Math.round(matching.reduce((s, r) => s + r.operations, 0) / matching.length);
          }
        }
        return point;
      }),
    };
  }, [rows, metric]);

  const totals = useMemo(() => {
    if (rows.length === 0) return null;
    return {
      rows: rows.length,
      algorithms: new Set(rows.map((r) => r.algorithm)).size,
      fastest: rows.reduce((min, r) => (r.execution_time_ms < min.execution_time_ms ? r : min)),
      slowest: rows.reduce((max, r) => (r.execution_time_ms > max.execution_time_ms ? r : max)),
    };
  }, [rows]);

  function toggle<T>(list: T[], value: T, setter: (v: T[]) => void) {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Analysis"
        title="Performance analysis"
        description="Benchmark the algorithms on generated datasets and read the measured running times. Every number is timed with perf_counter_ns on this machine — nothing is interpolated or estimated."
        actions={
          <Button
            variant="primary"
            icon={<Zap />}
            disabled={run.isPending}
            onClick={() => {
              run.mutate(
                {
                  algorithms: selectedAlgorithms.length ? selectedAlgorithms : undefined,
                  sizes: selectedSizes.length ? selectedSizes : undefined,
                  repeats,
                  persist: true,
                },
                { onSuccess: (data) => setLiveRows(data.rows) }
              );
            }}
          >
            {run.isPending ? "Benchmarking…" : "Run benchmark"}
          </Button>
        }
      />

      {run.isError ? <ErrorState error={run.error} /> : null}

      <Card className="mb-6">
        <CardHeader
          icon={<Gauge />}
          title="Benchmark configuration"
          subtitle="Leave a group empty to use the documented defaults"
        />
        <CardBody className="space-y-5">
          {options.isLoading ? (
            <Spinner label="Loading options" />
          ) : options.isError ? (
            <ErrorState error={options.error} />
          ) : (
            <>
              <div>
                <p className="dt-label mb-2">Algorithms</p>
                <div className="flex flex-wrap gap-1.5">
                  {(options.data?.algorithms ?? []).map((algo) => {
                    const on = selectedAlgorithms.includes(algo);
                    return (
                      <button
                        key={algo}
                        type="button"
                        onClick={() => toggle(selectedAlgorithms, algo, setSelectedAlgorithms)}
                        className={cn(
                          "rounded-control border px-2.5 py-1 text-[12px] transition-colors duration-fast",
                          on
                            ? "border-brand bg-brand text-txt-inverse"
                            : "border-line bg-canvas text-txt-muted hover:border-line-strong hover:text-txt"
                        )}
                      >
                        {algo}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <p className="dt-label mb-2">Input sizes</p>
                <div className="flex flex-wrap gap-1.5">
                  {(options.data?.sizes ?? []).map((size) => {
                    const on = selectedSizes.includes(size);
                    return (
                      <button
                        key={size}
                        type="button"
                        onClick={() => toggle(selectedSizes, size, setSelectedSizes)}
                        className={cn(
                          "rounded-control border px-2.5 py-1 text-[12px] tabular-nums transition-colors duration-fast",
                          on
                            ? "border-brand bg-brand-soft text-brand"
                            : "border-line bg-canvas text-txt-muted hover:border-line-strong hover:text-txt"
                        )}
                      >
                        {formatInt(size)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <label className="block max-w-[220px]">
                <span className="dt-label">Repeats (median reported)</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="dt-input mt-1"
                  value={repeats}
                  onChange={(e) =>
                    setRepeats(Math.max(1, Math.min(10, Number(e.target.value) || 1)))
                  }
                />
              </label>
            </>
          )}
        </CardBody>
      </Card>

      {totals ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile icon={<Activity />} label="Measured rows" value={formatInt(totals.rows)} />
          <StatTile
            icon={<ListFilter />}
            label="Algorithms"
            value={formatInt(totals.algorithms)}
          />
          <StatTile
            icon={<TrendingUp />}
            label="Fastest"
            value={formatMs(totals.fastest.execution_time_ms)}
            hint={totals.fastest.algorithm}
          />
          <StatTile
            icon={<Timer />}
            label="Slowest"
            value={formatMs(totals.slowest.execution_time_ms)}
            hint={totals.slowest.algorithm}
          />
        </div>
      ) : null}

      {rows.length === 0 ? (
        <Card className="mt-6">
          {stored.isLoading ? (
            <Spinner label="Loading stored benchmarks" />
          ) : (
            <EmptyState
              icon={<Gauge />}
              title="No benchmark data"
              description="Run a benchmark above, or process some documents — pipeline timings are stored too."
            />
          )}
        </Card>
      ) : (
        <div className="mt-6 space-y-6">
          <Card>
            <CardHeader
              icon={<TrendingUp />}
              title="Running time vs input size"
              subtitle={metric === "time" ? "Median of repeats, milliseconds" : "Mean operation count"}
              actions={
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    className={cn(
                      "dt-pill transition-colors duration-fast",
                      metric === "time"
                        ? "bg-brand text-txt-inverse"
                        : "bg-canvas-section text-txt-muted hover:bg-canvas-hover"
                    )}
                    onClick={() => setMetric("time")}
                  >
                    Time
                  </button>
                  <button
                    type="button"
                    className={cn(
                      "dt-pill transition-colors duration-fast",
                      metric === "operations"
                        ? "bg-brand text-txt-inverse"
                        : "bg-canvas-section text-txt-muted hover:bg-canvas-hover"
                    )}
                    onClick={() => setMetric("operations")}
                  >
                    Operations
                  </button>
                </div>
              }
            />
            <CardBody>
              <ResponsiveContainer width="100%" height={340}>
                <LineChart data={sizeSeries.data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis
                    dataKey="size"
                    stroke={AXIS}
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(v) => formatInt(Number(v))}
                  />
                  <YAxis
                    stroke={AXIS}
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(v) =>
                      metric === "time" ? `${Number(v).toFixed(2)}` : formatInt(Number(v))
                    }
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #E5E7EB",
                      boxShadow: "0 8px 24px -6px rgba(23,23,23,0.12)",
                      fontSize: 12,
                    }}
                    formatter={(value: number) =>
                      metric === "time" ? formatMs(value) : formatInt(value)
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {sizeSeries.algorithms.map((algo, i) => (
                    <Line
                      key={algo}
                      type="monotone"
                      dataKey={algo}
                      stroke={PALETTE[i % PALETTE.length]}
                      strokeWidth={1.8}
                      dot={{ r: 2.5 }}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              icon={<Timer />}
              title="Average time per algorithm"
              subtitle="Averaged across every measured input size"
            />
            <CardBody>
              <ResponsiveContainer width="100%" height={Math.max(220, byAlgorithm.length * 42)}>
                <BarChart
                  layout="vertical"
                  data={byAlgorithm.map(([algo, algoRows]) => ({
                    algorithm: algo,
                    avg: algoRows.reduce((s, r) => s + r.execution_time_ms, 0) / algoRows.length,
                  }))}
                  margin={{ top: 8, right: 24, bottom: 8, left: 40 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
                  <XAxis
                    type="number"
                    stroke={AXIS}
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(v) => formatMs(Number(v))}
                  />
                  <YAxis
                    type="category"
                    dataKey="algorithm"
                    stroke={AXIS}
                    fontSize={11}
                    tickLine={false}
                    width={120}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #E5E7EB",
                      boxShadow: "0 8px 24px -6px rgba(23,23,23,0.12)",
                      fontSize: 12,
                    }}
                    formatter={(value: number) => [formatMs(value), "Average"]}
                  />
                  <Bar dataKey="avg" radius={[0, 4, 4, 0]}>
                    {byAlgorithm.map((_, i) => (
                      <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              icon={<ListFilter />}
              title="All measurements"
              subtitle={`${formatInt(rows.length)} rows`}
            />
            <div className="max-h-[520px] overflow-auto">
              <table className="dt-table">
                <thead className="sticky top-0 z-10">
                  <tr>
                    <th>Algorithm</th>
                    <th>Dataset</th>
                    <th>Case</th>
                    <th className="text-right">Size</th>
                    <th className="text-right">Time</th>
                    <th className="text-right">Operations</th>
                    <th className="text-right">Memory</th>
                    <th className="text-right">Repeats</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i}>
                      <td className="font-medium text-txt">{row.algorithm}</td>
                      <td className="text-txt-muted">{humanize(row.dataset_type)}</td>
                      <td>
                        <StatusBadge
                          tone={
                            row.case_type === "worst"
                              ? "rose"
                              : row.case_type === "best"
                                ? "green"
                                : "blue"
                          }
                        >
                          {row.case_type}
                        </StatusBadge>
                      </td>
                      <td className="text-right tabular-nums">{formatInt(row.input_size)}</td>
                      <td className="text-right tabular-nums">{formatMs(row.execution_time_ms)}</td>
                      <td className="text-right tabular-nums">{formatInt(row.operations)}</td>
                      <td className="text-right tabular-nums">{formatBytes(row.memory_bytes)}</td>
                      <td className="text-right tabular-nums">{row.repeats}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
