import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { sanitizeResourceName, type ParsedServer } from "./jsonImport";
import type { components } from "@/lib/api/types";

type RegistryServer = components["schemas"]["RegistryServerOut"];

interface Props {
  server: RegistryServer;
  /** True while the parent's importBatch mutation is in flight. */
  importing: boolean;
  onBack: () => void;
  onAdd: (parsed: ParsedServer) => void;
}

/**
 * The "Use" step for an installable registry server: an editable Name
 * (seeded from the sanitized registry id), a read-only command/url preview,
 * and one input per declared env var (password input for secrets). On Add it
 * builds a {@link ParsedServer} for the dialog's existing import pipeline.
 */
export function RegistryServerForm({ server, importing, onBack, onAdd }: Props) {
  const { t } = useTranslation();
  const draft = server.draft!;
  const [name, setName] = useState(() => sanitizeResourceName(server.name));
  const [values, setValues] = useState<Record<string, string>>({});

  const preview =
    draft.transport_type === "stdio" ? [draft.command, ...draft.args].join(" ") : draft.url;

  function handleAdd() {
    onAdd({
      name,
      transportType: draft.transport_type,
      command: draft.command,
      args: draft.args,
      url: draft.url,
      env: draft.env.map((e) => ({
        key: e.key,
        value: values[e.key] ?? "",
        isSecret: e.is_secret,
      })),
    });
  }

  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">
        {t("mcp.registry.configure", { name: server.title || server.name })}
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="registry-name">{t("mcp.registry.nameLabel")}</Label>
        <Input
          id="registry-name"
          value={name}
          onChange={(e) => setName(sanitizeResourceName(e.target.value))}
        />
      </div>
      <div className="rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs break-all text-muted-foreground">
        {preview}
      </div>
      {draft.env.length > 0 ? (
        <div className="space-y-3">
          {draft.env.map((e) => (
            <div key={e.key} className="space-y-1.5">
              <Label htmlFor={`registry-env-${e.key}`}>
                {e.key}
                {e.required ? <span className="ml-0.5 text-destructive">*</span> : null}
              </Label>
              {e.is_secret ? (
                <PasswordInput
                  id={`registry-env-${e.key}`}
                  value={values[e.key] ?? ""}
                  onChange={(ev) => setValues((p) => ({ ...p, [e.key]: ev.target.value }))}
                />
              ) : (
                <Input
                  id={`registry-env-${e.key}`}
                  value={values[e.key] ?? ""}
                  onChange={(ev) => setValues((p) => ({ ...p, [e.key]: ev.target.value }))}
                />
              )}
              {e.description ? (
                <p className="text-xs text-muted-foreground">{e.description}</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      <div className="flex justify-between gap-2">
        <Button variant="outline" onClick={onBack} disabled={importing}>
          {t("mcp.import.back")}
        </Button>
        <Button onClick={handleAdd} disabled={importing || name.trim() === ""}>
          {importing ? t("common.saving") : t("mcp.registry.add")}
        </Button>
      </div>
    </div>
  );
}
