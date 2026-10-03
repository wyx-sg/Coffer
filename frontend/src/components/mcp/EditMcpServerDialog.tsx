// frontend/src/components/mcp/EditMcpServerDialog.tsx
// Edit an MCP server (boards Mcp-Edit / Mcp-EditStdio / Mcp-Edit-SaveFailed).
// Controlled: the detail header renders the Edit button. The name is shown fixed
// — it prefixes every tool name agents see, so the daemon refuses to change it
// (409 NAME_IMMUTABLE). The description (only you see it), how the server is
// reached (URL, or command + arguments + working directory), its Environment /
// Headers rows (plain text, or a secret from Coffer) and its timeouts are
// fields; every other key of the stored config is kept as it was
// (editMcpServerSave.ts `configTextFrom`).
//
// "Test" runs the unsaved form (useMcpConfigTest) and saves nothing. New secrets
// are written before the PATCH, and one that waits for approval says so once
// saved (useSaveMcpServerEdit). A failed save stays here as a danger-soft block
// with the edits intact, and Save becomes Retry.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, Play, RefreshCw } from "lucide-react";

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
import { useMcpConfigTest } from "@/lib/hooks/useMcpAddFlow";
import { useSaveMcpServerEdit } from "@/lib/hooks/useMcpServerMutations";
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import { shellSplit } from "@/lib/mcp/shellTokens";
import { AddTestResult } from "./add/AddTestResult";
import { EnvRowsField } from "./env/EnvRowsField";
import { configTestBodyOf } from "./env/configTestBody";
import { rowsOf } from "@/lib/mcp/serverRows";
import { TransportInputs, WorkingDirInput } from "./env/TransportInputs";
import { ServerTimeoutFields } from "./ServerTimeoutFields";
import { timeoutsOf, type Timeouts } from "@/lib/mcp/serverTimeouts";
import { configTextFrom, transportFieldsOf, type TransportForm } from "@/lib/mcp/editMcpServerSave";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const quote = (a: string) =>
  a === "" || /[\s'"\\$`]/.test(a) ? `'${a.replace(/'/g, `'\\''`)}'` : a;

const initialRows = (resource: ResourceOut): KeyValueSecretRow[] =>
  rowsOf(resource.config, transportFieldsOf(resource.config).plain);

export function EditMcpServerDialog({ resource, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const http = transportFieldsOf(resource.config).type === "http";
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [cwd, setCwd] = useState("");
  const [rows, setRows] = useState<KeyValueSecretRow[] | null>(null);
  const [focusRow, setFocusRow] = useState<number | undefined>();
  const [timeouts, setTimeouts] = useState<Timeouts>(() => timeoutsOf(resource.config));
  const [testedKey, setTestedKey] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const save = useSaveMcpServerEdit();
  const test = useMcpConfigTest();

  // A fresh form from the stored config every time the dialog opens.
  useEffect(() => {
    if (!open) return;
    const f = transportFieldsOf(resource.config);
    setDescription(resource.description ?? "");
    setUrl(f.url);
    setCommand(f.command);
    setArgsText(f.args.map(quote).join(" "));
    setCwd(f.cwd);
    const loaded = initialRows(resource);
    setRows(loaded);
    setTimeouts(timeoutsOf(resource.config));
    setTestedKey(null);
    setTestError(null);
    save.reset();
    test.reset();
    // `save`/`test` are stable per mount; re-seeding is keyed on the dialog opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resource]);

  const args = shellSplit(argsText);
  const form: TransportForm = {
    type: http ? "http" : "stdio",
    url,
    command,
    args: args ?? [],
    cwd,
    rows: rows ?? [],
  };
  // A result is shown only for the form it tested; any edit makes it stale.
  const formKey = JSON.stringify([form, timeouts]);
  const invalid = http ? !/^https?:\/\/\S+$/i.test(url.trim()) : !command.trim() || args === null;

  const onSave = () =>
    save.mutate(
      {
        resource,
        description,
        configText: configTextFrom(resource.config, form),
        rows: form.rows,
        timeouts,
      },
      { onSuccess: () => onOpenChange(false) },
    );
  const onTest = () => {
    setTestError(null);
    let body;
    try {
      body = configTestBodyOf(resource.name, resource.config, form, timeouts);
    } catch (e) {
      setTestError(e instanceof Error ? e.message : String(e));
      return;
    }
    setTestedKey(formKey);
    test.mutate(body);
  };
  const result = test.data && testedKey === formKey ? test.data : null;
  const busy = save.isPending || test.isPending;
  /** "Add the variable": a row for what the server said it needs. */
  const addVariable = (key: string) => {
    const at = (rows ?? []).findIndex((r) => r.key === key);
    if (at >= 0) return setFocusRow(at);
    setRows([...(rows ?? []), { key, value: { kind: "plain", value: "" } }]);
    setFocusRow((rows ?? []).length);
  };

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
            <Label htmlFor="edit-description">{t("mcp.edit.descriptionLabel")}</Label>
            <Input
              id="edit-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <p className="text-xs text-text-muted">{t("mcp.edit.descriptionHelp")}</p>
          </div>
          <TransportInputs
            http={http}
            url={url}
            command={command}
            argsText={argsText}
            argsInvalid={args === null}
            onUrl={setUrl}
            onCommand={setCommand}
            onArgs={setArgsText}
          />
          {rows !== null ? (
            <EnvRowsField http={http} rows={rows} onChange={setRows} focusRow={focusRow} />
          ) : null}
          {http ? null : <WorkingDirInput value={cwd} onChange={setCwd} />}
          <ServerTimeoutFields
            value={timeouts}
            onChange={setTimeouts}
            idPrefix="edit-timeout"
            showSpawn={!http}
          />
          {result ? (
            <AddTestResult
              result={result}
              transport={http ? "http" : "stdio"}
              server={resource.name}
              editing
              onAddVariable={addVariable}
            />
          ) : null}
          {testError || test.error ? (
            <Alert variant="error">
              <AlertDescription>
                {testError ?? (test.error ? translateApiError(t, test.error) : null)}
              </AlertDescription>
            </Alert>
          ) : null}
          {save.error ? (
            <div role="alert" className="flex flex-col gap-1 rounded-lg bg-danger-soft p-3">
              <p className="flex items-center gap-2 text-sm font-label text-text">
                <CircleAlert aria-hidden className="size-4 shrink-0 text-danger" />
                {t("mcp.edit.saveFailed", { name: resource.name })}
              </p>
              <p className="pl-6 text-xs leading-snug text-text-muted">
                {translateApiError(t, save.error)} {t("mcp.edit.saveFailedBody")}
              </p>
            </div>
          ) : null}
        </div>
        <DialogFooter className="sm:justify-between">
          <Button variant="outline" onClick={onTest} disabled={busy || invalid}>
            {test.data ? <RefreshCw /> : <Play />}
            {test.isPending
              ? t("mcp.edit.testing")
              : test.data
                ? t("mcp.edit.testAgain")
                : t("mcp.edit.test")}
          </Button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={save.isPending}>
              {t("common.cancel")}
            </Button>
            <Button onClick={onSave} disabled={busy || invalid}>
              {save.isPending
                ? t("common.saving")
                : save.error
                  ? t("common.retry")
                  : t("common.save")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
