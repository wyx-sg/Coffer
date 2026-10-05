// frontend/src/components/mcp/add/ServerForm.tsx — the Add server dialog's
// one-server form (boards Mcp-Add-TestPassed / Mcp-Add-Http / Mcp-Add-Errors).
//
// Opened prefilled from a paste that held one server, or empty from the type
// choice. Test runs the unsaved form (`POST /resources/mcp_server/test-config`,
// spec mcp-gateway "Test an unsaved server config before adding it") and shows
// what it found before Add server; nothing is saved by it, and an edit after
// the test retires its result. Add registers the server, which is tested once
// more on its page. A name another server has is said under the field, both
// before submit (from the list) and when the daemon answers 409. The footer is
// Test (left) · Cancel · Add server; the type bar's Change goes back to step 1.
import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import { translateApiError } from "@/lib/api/errors";
import { useMcpConfigTest } from "@/lib/hooks/useMcpAddFlow";
import type { ParsedServer } from "@/lib/mcp/pasteParse";
import { shellSplit } from "@/lib/mcp/shellTokens";
import type { FailedServer, NewServer, ReachIntent } from "@/lib/mcp/importMcpServers";
import { missingSecretValues } from "@/lib/mcp/importMcpServers";
import { askedKeysOf, keptRows, promoteAsked, rowsFromParsed } from "@/lib/mcp/serverRows";
import { EnvRowsField } from "../env/EnvRowsField";
import { TransportInputs, WorkingDirInput } from "../env/TransportInputs";
import { AddTestResult } from "./AddTestResult";
import { addTestBodyOf, testKeyOf } from "./addTestBody";
import { NameField } from "./NameField";
import { nameSendable } from "./nameProblem";
import { ReachPick } from "./ReachPick";

interface Props {
  initial: ParsedServer;
  /** Names already registered. */
  taken: ReadonlySet<string>;
  /** The type bar's Change: back to the paste box and the type choice. */
  onChangeType: () => void;
  onCancel: () => void;
  pending: boolean;
  /** The daemon's refusal of the last attempt, if any. */
  failure: FailedServer | null;
  onSubmit: (server: NewServer, reach: ReachIntent) => void;
}

/** One argument as a shell would need it typed, so splitting the joined line
 *  gives the same arguments back. */
function quoteArg(arg: string): string {
  return arg === "" || /[\s'"\\$`]/.test(arg) ? `'${arg.replace(/'/g, `'\\''`)}'` : arg;
}

export function ServerForm({
  initial,
  taken,
  onChangeType,
  onCancel,
  pending,
  failure,
  onSubmit,
}: Props) {
  const { t } = useTranslation();
  const type = initial.transportType;
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState("");
  const [cwd, setCwd] = useState("");
  const [command, setCommand] = useState(initial.command);
  const [argsText, setArgsText] = useState(initial.args.map(quoteArg).join(" "));
  const [url, setUrl] = useState(initial.url);
  const [rows, setRows] = useState<KeyValueSecretRow[]>(() => rowsFromParsed(initial.env, true));
  const [asked] = useState(() => askedKeysOf(initial.env));
  const [focusRow, setFocusRow] = useState<number | undefined>();
  const [reach, setReach] = useState<ReachIntent>({ mode: "everywhere" });
  const test = useMcpConfigTest();
  const [testedKey, setTestedKey] = useState<string | null>(null);
  // Leaving the form stops a test still running.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => test.cancel(), []);

  const takenNow = failure?.nameTaken && failure.name === name ? new Set([...taken, name]) : taken;
  const args = shellSplit(argsText);
  const server: NewServer = {
    name,
    description,
    cwd: type === "stdio" ? cwd : "",
    transportType: type,
    command: type === "stdio" ? command.trim() : "",
    args: type === "stdio" ? (args ?? []) : [],
    url: type === "http" ? url.trim() : "",
    env: promoteAsked(keptRows(rows), asked).map((r) => ({
      ...r,
      key: r.key.trim(),
    })),
  };
  // Keys the paste flagged secret without a value stay asked for until typed in.
  const unfilled = rows.filter(
    (r) => asked.has(r.key.trim()) && r.value.kind === "plain" && r.value.value === "",
  );
  const targetOk =
    type === "stdio"
      ? server.command !== "" && args !== null
      : /^https?:\/\/\S+$/i.test(server.url);
  const testBody = addTestBodyOf(server);
  const formKey = testKeyOf(testBody);
  const result = test.data && testedKey === formKey ? test.data : null;
  const canTest =
    !test.isPending &&
    targetOk &&
    missingSecretValues(server).length === 0 &&
    unfilled.length === 0;
  const runTest = () => {
    setTestedKey(formKey);
    test.mutate(testBody);
  };
  /** "Add the variable": a row for what the server said it needs. */
  const addVariable = (key: string) => {
    const at = rows.findIndex((r) => r.key === key);
    if (at >= 0) return setFocusRow(at);
    setRows([...rows, { key, value: { kind: "plain", value: "" } }]);
    setFocusRow(rows.length);
  };
  const canAdd =
    !pending &&
    nameSendable(name, takenNow) &&
    targetOk &&
    missingSecretValues(server).length === 0 &&
    unfilled.length === 0;

  return (
    <>
      <div className="flex items-center gap-2 rounded-lg bg-surface-sunken px-3 py-2 text-xs">
        <span className="font-label text-text">{t(`mcp.add.type.${type}`)}</span>
        <span className="text-text-muted">{t(`mcp.add.type.${type}Runs`)}</span>
        <Button
          variant="link"
          size="sm"
          className="ml-auto h-auto px-0"
          onClick={onChangeType}
          disabled={pending}
        >
          {t("mcp.add.change")}
        </Button>
      </div>
      <div className="space-y-4">
        <NameField
          id="add-server-name"
          value={name}
          onChange={setName}
          taken={takenNow}
          help={t("mcp.add.nameHelp", { name: name || "name" })}
        />
        <div className="space-y-1.5">
          <Label htmlFor="add-server-description">{t("mcp.edit.descriptionLabel")}</Label>
          <Input
            id="add-server-description"
            value={description}
            placeholder={t("mcp.add.descriptionPlaceholder")}
            onChange={(e) => setDescription(e.target.value)}
          />
          <p className="text-xs text-text-muted">{t("mcp.edit.descriptionHelp")}</p>
        </div>
        <TransportInputs
          idPrefix="add-server"
          http={type === "http"}
          url={url}
          command={command}
          argsText={argsText}
          argsInvalid={args === null}
          urlHelp={t("mcp.add.urlHelp")}
          onUrl={setUrl}
          onCommand={setCommand}
          onArgs={setArgsText}
        />
        <EnvRowsField http={type === "http"} rows={rows} onChange={setRows} focusRow={focusRow} />
        {unfilled.map((r) => (
          <p key={r.key} className="text-xs text-text-muted">
            {t("mcp.add.secretMissing", { key: r.key })}
          </p>
        ))}
        {type === "stdio" ? (
          <WorkingDirInput idPrefix="add-server" value={cwd} onChange={setCwd} />
        ) : null}
        {result ? (
          <AddTestResult
            result={result}
            transport={type}
            server={name}
            onAddVariable={addVariable}
          />
        ) : null}
        {test.error && testedKey === formKey ? (
          <Alert variant="error">
            <AlertDescription>{translateApiError(t, test.error)}</AlertDescription>
          </Alert>
        ) : null}
        {failure && !failure.nameTaken ? (
          <Alert variant="error">
            <AlertDescription>{failure.message}</AlertDescription>
          </Alert>
        ) : null}
        <ReachPick value={reach} onChange={setReach} busy={pending} />
      </div>
      <DialogFooter>
        <Button variant="outline" className="sm:mr-auto" disabled={!canTest} onClick={runTest}>
          {result ? <RefreshCw aria-hidden /> : <Play aria-hidden />}
          {test.isPending
            ? t("mcp.edit.testing")
            : result
              ? t("mcp.edit.testAgain")
              : t("mcp.edit.test")}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={pending}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!canAdd} onClick={() => onSubmit(server, reach)}>
          {pending ? t("mcp.add.adding") : t("mcp.add.addServer")}
        </Button>
      </DialogFooter>
    </>
  );
}
