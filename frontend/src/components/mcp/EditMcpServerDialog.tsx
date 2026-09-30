// frontend/src/components/mcp/EditMcpServerDialog.tsx
// Edit an MCP server (board Mcp-Edit). Controlled: the detail header renders
// the Edit button. The name is shown fixed — it prefixes every tool name agents
// see, so the daemon refuses to change it (409 NAME_IMMUTABLE). The title, how
// the server is reached (URL, or command + arguments), its plain env / header
// values, its stored secrets and its timeouts are fields; every other key of
// the stored config is kept as it was (editMcpServerSave.ts `configTextFrom`).
// Secrets are written before the PATCH, and a replaced secret that waits for
// approval says so once saved (useSaveMcpServerEdit).
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FixedNameField } from "@/components/resource/FixedName";
import { translateApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { useSaveMcpServerEdit } from "@/lib/hooks/useMcpServerMutations";
import type { ParsedEnvVar } from "@/lib/mcp/pasteParse";
import { shellSplit } from "@/lib/mcp/shellTokens";
import { KeyValueRows } from "./add/KeyValueRows";
import { SecretRowEditor, type CredRow } from "./SecretRowEditor";
import { ServerTimeoutFields } from "./ServerTimeoutFields";
import { timeoutsOf, type Timeouts } from "./serverTimeouts";
import { configTextFrom, secretRefsOf, transportFieldsOf } from "./editMcpServerSave";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Open with the first stored secret ready to replace. */
  focus?: "secret";
}

function credRowsOf(config: unknown): CredRow[] {
  return Object.entries(secretRefsOf(config)).map(([name, ref], i) => ({
    id: i,
    name,
    value: "",
    originalRef: ref,
    originalName: name,
  }));
}

const quote = (a: string) =>
  a === "" || /[\s'"\\$`]/.test(a) ? `'${a.replace(/'/g, `'\\''`)}'` : a;

export function EditMcpServerDialog({ resource, open, onOpenChange, focus }: Props) {
  const { t } = useTranslation();
  const initial = transportFieldsOf(resource.config);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [plain, setPlain] = useState<ParsedEnvVar[]>([]);
  const [creds, setCreds] = useState<CredRow[]>([]);
  const [timeouts, setTimeouts] = useState<Timeouts>(() => timeoutsOf(resource.config));
  const save = useSaveMcpServerEdit();

  // A fresh form from the stored config every time the dialog opens.
  useEffect(() => {
    if (!open) return;
    const f = transportFieldsOf(resource.config);
    setTitle(resource.title ?? "");
    setUrl(f.url);
    setCommand(f.command);
    setArgsText(f.args.map(quote).join(" "));
    setPlain(f.plain.map((p) => ({ ...p, isSecret: false })));
    setCreds(credRowsOf(resource.config));
    setTimeouts(timeoutsOf(resource.config));
    save.reset();
    // `save` is stable per mount; re-seeding is keyed on the dialog opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resource]);

  const http = initial.type === "http";
  const args = shellSplit(argsText);
  const onSave = () =>
    save.mutate(
      {
        resource,
        description: resource.description ?? "",
        title,
        configText: configTextFrom(resource.config, {
          type: initial.type,
          url,
          command,
          args: args ?? [],
          plain,
        }),
        creds,
        timeouts,
      },
      { onSuccess: () => onOpenChange(false) },
    );
  const invalid = http ? !/^https?:\/\/\S+$/i.test(url.trim()) : !command.trim() || args === null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[640px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("mcp.edit.title", { name: resource.name })}</DialogTitle>
          <DialogDescription>{t("mcp.edit.subtitle")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <FixedNameField id="edit-name" name={resource.name} hint={t("mcp.edit.fixedNameHint")} />
          <div className="space-y-1.5">
            <Label htmlFor="edit-title">{t("mcp.edit.titleLabel")}</Label>
            <Input id="edit-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <p className="text-xs text-text-muted">{t("mcp.edit.titleHelp")}</p>
          </div>
          {http ? (
            <div className="space-y-1.5">
              <Label htmlFor="edit-url" required>
                {t("mcp.add.url")}
              </Label>
              <Input
                id="edit-url"
                className="font-mono"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <p className="text-xs text-text-muted">{t("mcp.edit.urlHelp")}</p>
            </div>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="edit-command" required>
                  {t("mcp.add.command")}
                </Label>
                <Input
                  id="edit-command"
                  className="font-mono"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-args">{t("mcp.add.args")}</Label>
                <Input
                  id="edit-args"
                  className="font-mono"
                  value={argsText}
                  aria-invalid={args === null || undefined}
                  onChange={(e) => setArgsText(e.target.value)}
                />
                {args === null ? (
                  <p className="text-xs text-danger" role="alert">
                    {t("mcp.add.argsQuote")}
                  </p>
                ) : null}
              </div>
            </>
          )}
          <KeyValueRows
            idPrefix="edit-plain"
            label={http ? t("mcp.add.headers") : t("mcp.add.env")}
            keyPlaceholder={http ? "X-Region" : "LOG_LEVEL"}
            rows={plain}
            onChange={setPlain}
            secretToggle={false}
          />
          {open ? (
            <SecretRowEditor
              creds={creds}
              focusFirst={focus === "secret"}
              onUpdate={(idx, patch) =>
                setCreds((c) => c.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
              }
              onRemove={(idx) => setCreds((c) => c.filter((_, i) => i !== idx))}
              onAdd={() =>
                setCreds((c) => [
                  ...c,
                  { id: Date.now(), name: "", value: "", originalRef: null, originalName: null },
                ])
              }
            />
          ) : null}
          <ServerTimeoutFields value={timeouts} onChange={setTimeouts} idPrefix="edit-timeout" />
          {save.error ? (
            <Alert variant="error">
              <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
            </Alert>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={save.isPending}>
            {t("common.cancel")}
          </Button>
          <Button onClick={onSave} disabled={save.isPending || invalid}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
