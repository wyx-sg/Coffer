// frontend/src/components/mcp/add/ServerForm.tsx — the Add server dialog's
// one-server form (boards Mcp-Add-TestPassed / Mcp-Add-Http / Mcp-Add-Errors).
//
// Opened prefilled from a paste that held one server, or empty from the type
// choice. Test runs the unsaved form (`POST /resources/mcp_server/test-config`,
// spec mcp-gateway "Test an unsaved server config before adding it") and shows
// what it found before Add server; nothing is saved by it, and an edit after
// the test retires its result. Add registers the server, which is tested once
// more on its page. A name another server has is said under the field, both
// before submit (from the list) and when the daemon answers 409.
import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import { useMcpConfigTest } from "@/lib/hooks/useMcpAddFlow";
import type { ParsedEnvVar, ParsedServer } from "@/lib/mcp/pasteParse";
import { shellSplit } from "@/lib/mcp/shellTokens";
import type { FailedServer, NewServer, ReachIntent } from "@/lib/mcp/importMcpServers";
import { missingSecretValues } from "@/lib/mcp/importMcpServers";
import { WorkingDirInput } from "../env/TransportInputs";
import { AddTestResult } from "./AddTestResult";
import { addTestBodyOf, testKeyOf } from "./addTestBody";
import { KeyValueRows } from "./KeyValueRows";
import { NameField } from "./NameField";
import { nameSendable } from "./nameProblem";
import { ReachPick } from "./ReachPick";

interface Props {
  initial: ParsedServer;
  /** Names already registered. */
  taken: ReadonlySet<string>;
  /** Set when the form came from a paste: offers Back to the paste box. */
  onBack?: () => void;
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
  onBack,
  onCancel,
  pending,
  failure,
  onSubmit,
}: Props) {
  const { t } = useTranslation();
  const [type, setType] = useState(initial.transportType);
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState("");
  const [cwd, setCwd] = useState("");
  const [command, setCommand] = useState(initial.command);
  const [argsText, setArgsText] = useState(initial.args.map(quoteArg).join(" "));
  const [url, setUrl] = useState(initial.url);
  const [rows, setRows] = useState<ParsedEnvVar[]>(initial.env);
  const [reach, setReach] = useState<ReachIntent>({ mode: "everywhere" });
  const test = useMcpConfigTest();
  const [testedKey, setTestedKey] = useState<string | null>(null);
  // Leaving the form stops a test still running.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => test.cancel(), []);

  const takenNow = failure?.nameTaken && failure.name === name ? new Set([...taken, name]) : taken;
  const args = shellSplit(argsText);
  const kept = rows.filter((r) => r.key.trim() !== "");
  const server: NewServer = {
    name,
    description,
    cwd: type === "stdio" ? cwd : "",
    transportType: type,
    command: type === "stdio" ? command.trim() : "",
    args: type === "stdio" ? (args ?? []) : [],
    url: type === "http" ? url.trim() : "",
    env: kept.map((r) => ({ ...r, key: r.key.trim() })),
  };
  const targetOk =
    type === "stdio"
      ? server.command !== "" && args !== null
      : /^https?:\/\/\S+$/i.test(server.url);
  const testBody = addTestBodyOf(server);
  const formKey = testKeyOf(testBody);
  const result = test.data && testedKey === formKey ? test.data : null;
  const canTest = !test.isPending && targetOk && missingSecretValues(server).length === 0;
  const runTest = () => {
    setTestedKey(formKey);
    test.mutate(testBody);
  };
  const canAdd =
    !pending &&
    nameSendable(name, takenNow) &&
    targetOk &&
    missingSecretValues(server).length === 0;

  return (
    <>
      <div className="flex items-center gap-2 rounded-lg bg-surface-sunken px-3 py-2 text-xs">
        <span className="font-label text-text">{t(`mcp.add.type.${type}`)}</span>
        <span className="text-text-muted">{t(`mcp.add.type.${type}Runs`)}</span>
        <Button
          variant="link"
          size="sm"
          className="ml-auto h-auto px-0"
          onClick={() => setType(type === "stdio" ? "http" : "stdio")}
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
        {type === "stdio" ? (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="add-server-command" required>
                {t("mcp.add.command")}
              </Label>
              <Input
                id="add-server-command"
                className="font-mono"
                spellCheck={false}
                value={command}
                onChange={(e) => setCommand(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="add-server-args">{t("mcp.add.args")}</Label>
              <Input
                id="add-server-args"
                className="font-mono"
                spellCheck={false}
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
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="add-server-url" required>
              {t("mcp.add.url")}
            </Label>
            <Input
              id="add-server-url"
              className="font-mono"
              spellCheck={false}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <p className="text-xs text-text-muted">{t("mcp.add.urlHelp")}</p>
          </div>
        )}
        <KeyValueRows
          idPrefix="add-server-row"
          label={type === "stdio" ? t("mcp.add.env") : t("mcp.add.headers")}
          keyPlaceholder={type === "stdio" ? "API_KEY" : "Authorization"}
          rows={rows}
          onChange={setRows}
          storedSecrets
        />
        {type === "stdio" ? <WorkingDirInput value={cwd} onChange={setCwd} /> : null}
        {result ? <AddTestResult result={result} transport={type} server={name} /> : null}
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
        {onBack ? (
          <Button variant="ghost" onClick={onBack} disabled={pending}>
            {t("mcp.add.back")}
          </Button>
        ) : null}
        <Button variant="outline" className="sm:mr-auto" disabled={!canTest} onClick={runTest}>
          {result ? <RefreshCw aria-hidden /> : <Play aria-hidden />}
          {test.isPending
            ? t("mcp.edit.testing")
            : result
              ? t("mcp.edit.testAgain")
              : t("mcp.edit.test")}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={pending}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!canAdd} onClick={() => onSubmit(server, reach)}>
          {pending ? t("mcp.add.adding") : t("mcp.add.addServer")}
        </Button>
      </DialogFooter>
    </>
  );
}
