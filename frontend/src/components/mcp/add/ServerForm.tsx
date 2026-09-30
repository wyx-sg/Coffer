// frontend/src/components/mcp/add/ServerForm.tsx — the Add server dialog's
// one-server form (boards Mcp-Add-TestPassed / Mcp-Add-Http / Mcp-Add-Errors).
//
// Opened prefilled from a paste that held one server, or empty from the type
// choice. Nothing is tested before Add — no route tests an unregistered config
// — so Add registers the server and the dialog tests it right after, on its
// page. A name another server has is said under the field, both before submit
// (from the list) and when the daemon answers 409.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ParsedEnvVar, ParsedServer } from "@/lib/mcp/pasteParse";
import { shellSplit } from "@/lib/mcp/shellTokens";
import type { FailedServer, NewServer, ReachIntent } from "../importMcpServers";
import { missingSecretValues } from "../importMcpServers";
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
  const [title, setTitle] = useState("");
  const [command, setCommand] = useState(initial.command);
  const [argsText, setArgsText] = useState(initial.args.map(quoteArg).join(" "));
  const [url, setUrl] = useState(initial.url);
  const [rows, setRows] = useState<ParsedEnvVar[]>(initial.env);
  const [reach, setReach] = useState<ReachIntent>({ mode: "everywhere" });

  const takenNow = failure?.nameTaken && failure.name === name ? new Set([...taken, name]) : taken;
  const args = shellSplit(argsText);
  const kept = rows.filter((r) => r.key.trim() !== "");
  const server: NewServer = {
    name,
    title,
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
          <Label htmlFor="add-server-title">{t("mcp.add.title")}</Label>
          <Input id="add-server-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <p className="text-xs text-text-muted">{t("mcp.add.titleHelp")}</p>
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
        />
        {failure && !failure.nameTaken ? (
          <Alert variant="error">
            <AlertDescription>{failure.message}</AlertDescription>
          </Alert>
        ) : null}
        <ReachPick value={reach} onChange={setReach} busy={pending} />
        <p className="text-xs text-text-muted">{t("mcp.add.testAfterAdd")}</p>
      </div>
      <DialogFooter>
        {onBack ? (
          <Button variant="ghost" className="sm:mr-auto" onClick={onBack} disabled={pending}>
            {t("mcp.add.back")}
          </Button>
        ) : null}
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
