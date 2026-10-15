import { useState } from "react";
import { FileStack, Plus, Trash2 } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
  type PillTone,
} from "../components/ui";
import { useDeleteTemplate, useSaveTemplate, useTemplates } from "../hooks/queries";
import { cn, humanize } from "../lib/utils";

export default function Templates() {
  const templates = useTemplates();
  const save = useSaveTemplate();
  const remove = useDeleteTemplate();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = (templates.data ?? []).find((tpl) => tpl.id === selectedId) ?? null;

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Configuration"
        title="Document templates"
        description="A template defines the required, optional and critical fields for a document type, along with the approved label aliases and the expected section order."
        actions={
          <Button
            variant="primary"
            icon={<Plus />}
            onClick={() => {
              const name = prompt("New template name (snake_case):");
              if (!name) return;
              save.mutate({
                body: {
                  name: name.trim().toLowerCase().replace(/\s+/g, "_"),
                  category: "custom",
                  description: "User-defined template.",
                  required_fields: [],
                  optional_fields: [],
                  critical_fields: [],
                  expected_sections: [],
                  section_order: [],
                  aliases: {},
                },
              });
            }}
          >
            New template
          </Button>
        }
      />

      {save.isError ? <ErrorState error={save.error} /> : null}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(240px,300px)_1fr]">
        <Card className="overflow-hidden self-start">
          <CardHeader
            icon={<FileStack />}
            title="Templates"
            subtitle={`${templates.data?.length ?? 0} defined`}
          />
          {templates.isLoading ? (
            <Spinner label="Loading templates" />
          ) : templates.isError ? (
            <CardBody>
              <ErrorState error={templates.error} />
            </CardBody>
          ) : (
            <ul>
              {(templates.data ?? []).map((tpl) => (
                <li key={tpl.id} className="border-b border-line-soft last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setSelectedId(tpl.id)}
                    className={cn(
                      "w-full px-4 py-2.5 text-left transition-colors duration-fast",
                      selectedId === tpl.id ? "bg-brand-soft" : "hover:bg-canvas-soft"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={cn(
                          "truncate text-[12.5px] font-medium",
                          selectedId === tpl.id ? "text-brand" : "text-txt"
                        )}
                      >
                        {humanize(tpl.name)}
                      </span>
                      <StatusBadge tone="slate">{tpl.category}</StatusBadge>
                    </div>
                    <p className="mt-0.5 text-[11.5px] text-txt-faint">
                      {tpl.required_fields.length} required · {tpl.critical_fields.length} critical
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="overflow-hidden">
          {!selected ? (
            <CardBody>
              <p className="py-16 text-center text-[12.5px] text-txt-faint">
                Select a template to view its fields and aliases.
              </p>
            </CardBody>
          ) : (
            <>
              <CardHeader
                icon={<FileStack />}
                title={humanize(selected.name)}
                subtitle={selected.description ?? undefined}
                actions={
                  selected.category === "custom" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Trash2 />}
                      className="text-pill-rose-txt hover:bg-pill-rose/40"
                      onClick={() => {
                        if (confirm(`Delete template "${selected.name}"?`)) {
                          remove.mutate(selected.id);
                          setSelectedId(null);
                        }
                      }}
                    >
                      Delete
                    </Button>
                  ) : (
                    <StatusBadge tone="blue">Built-in</StatusBadge>
                  )
                }
              />
              <CardBody className="space-y-5">
                <FieldList title="Required fields" fields={selected.required_fields} tone="green" />
                <FieldList title="Critical fields" fields={selected.critical_fields} tone="rose" />
                <FieldList title="Optional fields" fields={selected.optional_fields} tone="slate" />
                <FieldList
                  title="Expected sections"
                  fields={selected.expected_sections}
                  tone="blue"
                />

                {Object.keys(selected.aliases ?? {}).length > 0 ? (
                  <div>
                    <p className="dt-label mb-2">Approved label aliases</p>
                    <div className="space-y-1.5">
                      {Object.entries(selected.aliases).map(([field, aliases]) => (
                        <div key={field} className="flex flex-wrap items-baseline gap-2">
                          <span className="dt-mono w-40 shrink-0 text-brand">{field}</span>
                          <span className="text-[12px] text-txt-muted">{aliases.join(" · ")}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {selected.fields.length > 0 ? (
                  <div>
                    <p className="dt-label mb-2">Field definitions</p>
                    <div className="overflow-hidden rounded-panel border border-line">
                      <table className="dt-table">
                        <thead>
                          <tr>
                            <th>Field</th>
                            <th>Type</th>
                            <th>Required</th>
                            <th>Critical</th>
                            <th>Pattern</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selected.fields.map((field) => (
                            <tr key={field.id}>
                              <td className="font-medium">{field.name}</td>
                              <td className="text-[12.5px] text-txt-muted">{field.data_type}</td>
                              <td>
                                {field.required ? (
                                  <StatusBadge tone="green">Yes</StatusBadge>
                                ) : (
                                  <span className="text-txt-faint">—</span>
                                )}
                              </td>
                              <td>
                                {field.critical ? (
                                  <StatusBadge tone="rose">Yes</StatusBadge>
                                ) : (
                                  <span className="text-txt-faint">—</span>
                                )}
                              </td>
                              <td className="dt-mono text-[11px] text-txt-faint">
                                {field.validation_pattern ?? "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </CardBody>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function FieldList({
  title,
  fields,
  tone,
}: {
  title: string;
  fields: string[];
  tone: PillTone;
}) {
  if (!fields || fields.length === 0) return null;
  return (
    <div>
      <p className="dt-label mb-1.5">{title}</p>
      <div className="flex flex-wrap gap-1.5">
        {fields.map((field) => (
          <StatusBadge key={field} tone={tone}>
            {field}
          </StatusBadge>
        ))}
      </div>
    </div>
  );
}
