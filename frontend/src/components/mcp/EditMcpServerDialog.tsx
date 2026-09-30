// frontend/src/components/mcp/EditMcpServerDialog.tsx
// Edit an MCP server (boards Mcp-Edit / Mcp-EditStdio). Controlled: the detail
// header renders the Edit button. The name is shown fixed — it prefixes every
// tool name agents see, so the daemon refuses to change it (409
// NAME_IMMUTABLE). The description (only you see it), how the server is reached
// (URL, or command + arguments + working directory), its Environment / Headers
// rows — each Secret or Plain, a Secret one citing a stored secret or taking a
// new value — and its timeouts are fields; every other key of the stored
// config is kept as it was (editMcpServerSave.ts `configTextFrom`).
//
// "Test" runs the unsaved form (useMcpConfigTest) and saves nothing. Secrets
// are written before the PATCH, and a replaced secret that waits for approval
// says so once saved (useSaveMcpServerEdit).
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play, RefreshCw } from "lucide-react";

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
import type { ParsedEnvVar } from "@/lib/mcp/pasteParse";
import { shellSplit } from "@/lib/mcp/shellTokens";
import { KeyValueRows } from "./add/KeyValueRows";
import { ConfigTestResult } from "./env/ConfigTestResult";
import { configTestBodyOf } from "./env/configTestBody";
import { rowsOf } from "./env/rowsModel";
import { TransportInputs, WorkingDirInput } from "./env/TransportInputs";
import { ServerTimeoutFields } from "./ServerTimeoutFields";
import { timeoutsOf, type Timeouts } from "./serverTimeouts";
import { configTextFrom, transportFieldsOf, type TransportForm } from "./editMcpServerSave";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Open with the first stored secret's Replace already open and focused. */
  focus?: "secret";
}

const quote = (a: string) =>
  a === "" || /[\s'"\\$`]/.test(a) ? `'${a.replace(/'/g, `'\\''`)}'` : a;

/** The rows the dialog opens with; with `focus`, the first own stored secret
 *  starts in Replace (its typed-value input, which a blank value leaves as is). */
function initialRows(resource: ResourceOut, focus: Props["focus"]): ParsedEnvVar[] {
  const rows = rowsOf(resource.config, transportFieldsOf(resource.config).plain);
  if (focus !== "secret") return rows;
  const i = rows.findIndex((r) => r.storedRef);
  return rows.map((r, j) => (j === i ? { ...r, ref: null } : r));
}

export function EditMcpServerDialog({ resource, open, onOpenChange, focus }: Props) {
  const { t } = useTranslation();
  const http = transportFieldsOf(resource.config).type === "http";
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [cwd, setCwd] = useState("");
  const [rows, setRows] = useState<ParsedEnvVar[] | null>(null);
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
    setRows(initialRows(resource, focus));
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
      body = configTestBodyOf(resource.name, resource.config, form, timeouts, t);
    } catch (e) {
      setTestError(e instanceof Error ? e.message : String(e));
      return;
    }
    setTestedKey(formKey);
    test.mutate(body);
  };
  const result = test.data && testedKey === formKey ? test.data : null;
  const busy = save.isPending || test.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[620px] overflow-y-auto">
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
            <KeyValueRows
              idPrefix="edit-row"
              label={http ? t("mcp.add.headers") : t("mcp.add.env")}
              keyPlaceholder={http ? "Authorization" : "API_KEY"}
              addLabel={http ? t("mcp.env.addHeader") : t("mcp.env.addVariable")}
              rows={rows}
              onChange={setRows}
              storedSecrets
              focusRow={focus === "secret" ? rows.findIndex((r) => r.storedRef) : undefined}
            />
          ) : null}
          {http ? null : <WorkingDirInput value={cwd} onChange={setCwd} />}
          <ServerTimeoutFields
            value={timeouts}
            onChange={setTimeouts}
            idPrefix="edit-timeout"
            showSpawn={!http}
          />
          {result ? <ConfigTestResult result={result} /> : null}
          {testError || test.error ? (
            <Alert variant="error">
              <AlertDescription>
                {testError ?? (test.error ? translateApiError(t, test.error) : null)}
              </AlertDescription>
            </Alert>
          ) : null}
          {save.error ? (
            <Alert variant="error">
              <AlertDescription>{translateApiError(t, save.error)}</AlertDescription>
            </Alert>
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
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={save.isPending}>
              {t("common.cancel")}
            </Button>
            <Button onClick={onSave} disabled={busy || invalid}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
