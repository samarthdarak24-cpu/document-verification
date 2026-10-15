import { useState } from "react";
import { RotateCcw, Settings2 } from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useResetSettings, useSettings, useUpdateSetting } from "../hooks/queries";
import { humanize } from "../lib/utils";

export default function Settings() {
  const settings = useSettings();
  const update = useUpdateSetting();
  const reset = useResetSettings();

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Thresholds and policies used by the pipeline. Values are stored in the local database and read on every run, so changes apply immediately without a restart."
        actions={
          <Button
            icon={<RotateCcw />}
            disabled={reset.isPending}
            onClick={() => {
              if (confirm("Reset all settings to their documented defaults?")) reset.mutate();
            }}
          >
            {reset.isPending ? "Resetting…" : "Reset to defaults"}
          </Button>
        }
      />

      {reset.isSuccess ? (
        <div className="mb-4 rounded-panel border border-pill-green bg-pill-green/50 px-4 py-2.5 text-[12.5px] text-pill-green-txt">
          Settings restored to defaults.
        </div>
      ) : null}
      {update.isError ? <ErrorState error={update.error} /> : null}

      {settings.isLoading ? (
        <Spinner label="Loading settings" />
      ) : settings.isError ? (
        <ErrorState error={settings.error} />
      ) : (
        <div className="space-y-4">
          {(settings.data ?? []).map((setting) => (
            <SettingEditor
              key={setting.key}
              settingKey={setting.key}
              description={setting.description}
              value={setting.value}
              saving={update.isPending}
              onSave={(value) => update.mutate({ key: setting.key, value })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SettingEditor({
  settingKey,
  description,
  value,
  saving,
  onSave,
}: {
  settingKey: string;
  description: string | null;
  value: Record<string, unknown>;
  saving: boolean;
  onSave: (value: Record<string, unknown>) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(value).map(([k, v]) => [
        k,
        typeof v === "object" ? JSON.stringify(v) : String(v),
      ])
    )
  );

  function commit() {
    const parsed: Record<string, unknown> = {};
    for (const [key, raw] of Object.entries(draft)) {
      const original = value[key];
      if (typeof original === "number") {
        const num = Number(raw);
        parsed[key] = Number.isNaN(num) ? original : num;
      } else if (typeof original === "boolean") {
        parsed[key] = raw === "true" || raw === "True";
      } else {
        parsed[key] = raw;
      }
    }
    onSave(parsed);
  }

  return (
    <Card>
      <CardHeader
        icon={<Settings2 />}
        title={humanize(settingKey)}
        subtitle={description ?? undefined}
        actions={<StatusBadge tone="slate">{settingKey}</StatusBadge>}
      />
      <CardBody>
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          {Object.entries(draft).map(([key, raw]) => (
            <label key={key} className="block">
              <span className="dt-label">{humanize(key)}</span>
              {typeof value[key] === "boolean" ? (
                <select
                  className="dt-select mt-1"
                  value={raw}
                  onChange={(event) => setDraft((d) => ({ ...d, [key]: event.target.value }))}
                >
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              ) : (
                <input
                  className="dt-input mt-1"
                  value={raw}
                  onChange={(event) => setDraft((d) => ({ ...d, [key]: event.target.value }))}
                />
              )}
            </label>
          ))}
        </div>
        <div className="mt-4">
          <Button variant="primary" disabled={saving} onClick={commit}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
