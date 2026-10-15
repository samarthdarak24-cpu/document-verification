import { useParams } from "react-router-dom";
import { BookOpen, Compass, Timer } from "lucide-react";
import {
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useAlgorithms } from "../hooks/queries";
import { getUnit } from "../lib/units";
import UnitRunner from "../components/UnitRunner";

export default function UnitPage() {
  const { unit = "1" } = useParams();
  const algorithms = useAlgorithms();
  const meta = getUnit(unit);

  if (!meta) {
    return (
      <div>
        <PageHeader eyebrow="DAA Laboratory" title="Unknown unit" />
        <p className="text-sm text-txt-faint">
          Unit "{unit}" is not part of the mapped syllabus (Units I–VI).
        </p>
      </div>
    );
  }

  const unitAlgorithms = (algorithms.data ?? []).filter((a) =>
    meta.match.some((prefix) => a.unit.startsWith(prefix))
  );

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow={`DAA Syllabus · ${meta.roman}`}
        title={meta.title}
        description={meta.summary}
        actions={<StatusBadge tone="lavender">{meta.hours}</StatusBadge>}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.05fr_1fr]">
        <Card>
          <CardHeader
            icon={<BookOpen />}
            title="Syllabus coverage"
            subtitle="What this unit requires, and where it lives in DocuTrace"
          />
          <CardBody className="px-0 py-0">
            <table className="dt-table">
              <thead>
                <tr>
                  <th>Topic</th>
                  <th>Implementation</th>
                </tr>
              </thead>
              <tbody>
                {meta.topics.map((topic) => (
                  <tr key={topic.topic}>
                    <td className="font-medium text-txt">{topic.topic}</td>
                    <td className="text-[12.5px] text-txt-muted">{topic.where}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader
              icon={<Compass />}
              title="Why it matters here"
              subtitle="The genuine problem this unit solves"
            />
            <CardBody className="space-y-3 text-[13px] leading-relaxed text-txt-muted">
              {meta.rationale.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              icon={<Timer />}
              title="Complexity"
              subtitle="For the implementation that actually ships"
            />
            <CardBody className="px-0 py-0">
              <table className="dt-table">
                <thead>
                  <tr>
                    <th>Algorithm</th>
                    <th>Time</th>
                    <th>Space</th>
                  </tr>
                </thead>
                <tbody>
                  {meta.complexities.map((c) => (
                    <tr key={c.name}>
                      <td className="font-medium text-txt">{c.name}</td>
                      <td className="dt-mono text-[11.5px]">{c.time}</td>
                      <td className="dt-mono text-[11.5px]">{c.space}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        </div>
      </div>

      <div className="mt-6">
        <h2 className="mb-3 text-section">Interactive playground</h2>
        {algorithms.isLoading ? (
          <Spinner label="Loading algorithms" />
        ) : algorithms.isError ? (
          <ErrorState error={algorithms.error} />
        ) : unitAlgorithms.length === 0 ? (
          <Card>
            <CardBody>
              <p className="py-8 text-center text-sm text-txt-faint">
                No runnable algorithm is mapped to this unit yet.
              </p>
            </CardBody>
          </Card>
        ) : (
          <UnitRunner algorithms={unitAlgorithms} />
        )}
      </div>
    </div>
  );
}
