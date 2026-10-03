// frontend/src/components/mcp/add/AddTestResult.tsx — what testing an unsaved
// server config found, in the Add server form and the Edit dialog (boards
// Mcp-Add-TestPassed, Mcp-Add-Http, Mcp-Add-Errors, Mcp-Edit).
//
// Passed: a neutral block with a green check — "Test passed in 1.4 s · 26 tools,
// …" (or "Connected in 212 ms · …" for an HTTP server added), the first tool
// names, a warning for a name longer than model APIs accept, and the stderr lines
// behind Show. Failed: a danger block with why and the last stderr lines; a
// variable the server says it needs gets "Add the variable"; a failure that
// depends on this machine gets the hand-off when the daemon supplies one.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck, Plus } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import type { McpTestResult } from "@/lib/api/mcpTestConfig";
import { missingVariableOf } from "@/lib/mcp/testFailure";

/** How many tool names the result lists before "+ N more". */
const SHOWN = 7;
/** The longest tool name model APIs accept. */
const NAME_LIMIT = 64;

/** Error codes with a short reason of their own (`McpTestErrorCode`). */
const REASONS = new Set([
  "url_refused",
  "spawn_failed",
  "exited",
  "timeout",
  "initialize_failed",
  "connect_failed",
  "auth_rejected",
  "stored_secret_not_released",
  "unsupported_transport",
]);

/** Failures that depend on this machine (launcher, network, process). */
const MACHINE = new Set(["spawn_failed", "exited", "timeout", "connect_failed"]);

const seconds = (ms: number) => (ms / 1000).toFixed(1);

function Stderr({ lines }: { lines: string[] }) {
  return (
    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-surface px-2.5 py-2 font-mono text-2xs leading-relaxed text-text">
      {lines.join("\n")}
    </pre>
  );
}

interface Props {
  result: McpTestResult;
  transport: "stdio" | "http";
  /** The server's name, for the name agents see each tool under. */
  server: string;
  /** The Edit dialog: the server already exists, so "added" wording is dropped. */
  editing?: boolean;
  /** "Add the variable": add a row for the variable the server says it needs. */
  onAddVariable?: (key: string) => void;
}

function Failed({ result, editing, onAddVariable }: Omit<Props, "transport" | "server">) {
  const { t } = useTranslation();
  const stderr = result.stderr_tail ?? [];
  const code = result.error_code ?? "";
  const exited = code === "exited";
  const reason = REASONS.has(code)
    ? t(`mcp.edit.testReason.${code}`, { code: result.exit_code ?? "?" })
    : t("mcp.edit.testReason.other");
  const needs = missingVariableOf(result);
  const body =
    code === "stored_secret_not_released" && !editing
      ? t("mcp.add.test.storedSecret", { keys: (result.unreleased_secret_keys ?? []).join(", ") })
      : exited
        ? result.tool_count > 0
          ? t("mcp.add.test.stderrIntro")
          : t("mcp.add.test.exitedBody")
        : `${result.error_message ?? ""}${stderr.length > 0 ? ` ${t("mcp.add.test.stderrIntro")}` : ""}`;
  const handoff = MACHINE.has(code) && !needs ? result.handoff?.prompt : undefined;
  return (
    <div
      role="alert"
      data-testid="add-test-result"
      className="flex flex-col gap-2 rounded-lg bg-danger-soft p-3"
    >
      <p className="flex items-center gap-2 text-sm font-label text-text">
        <CircleAlert aria-hidden className="size-4 shrink-0 text-danger" />
        {t("mcp.edit.testFailed", { seconds: seconds(result.latency_ms), reason })}
      </p>
      <p className="text-xs leading-snug text-text-muted">
        {body}
        {editing ? ` ${t("mcp.edit.nothingSaved")}` : ""}
      </p>
      {stderr.length > 0 ? <Stderr lines={stderr} /> : null}
      {needs ? (
        <>
          <p className="text-xs leading-snug text-text">
            {t("mcp.add.test.needs", { key: needs })}
          </p>
          {onAddVariable ? (
            <div>
              <Button variant="outline" size="sm" onClick={() => onAddVariable(needs)}>
                <Plus aria-hidden /> {t("mcp.add.test.addVariable")}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
      {handoff ? (
        <div className="pt-0.5">
          <AgentHandoff prompt={handoff} size="sm" />
        </div>
      ) : null}
    </div>
  );
}

export function AddTestResult({ result, transport, server, editing, onAddVariable }: Props) {
  const { t } = useTranslation();
  const [showStderr, setShowStderr] = useState(false);
  const stderr = result.stderr_tail ?? [];

  if (!result.ok) return <Failed result={result} editing={editing} onAddVariable={onAddVariable} />;

  const tools = result.tools ?? [];
  const long = tools.find((tool) => `mcp__coffer__${server}__${tool.name}`.length > NAME_LIMIT);
  const head =
    transport === "http" && !editing
      ? t("mcp.add.test.connected", { ms: result.latency_ms })
      : t("mcp.add.test.passed", { seconds: seconds(result.latency_ms) });
  return (
    <div
      role="status"
      data-testid="add-test-result"
      className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface-sunken p-3 text-xs"
    >
      <p className="flex items-center gap-2 text-sm text-text">
        <CircleCheck aria-hidden className="size-4 shrink-0 text-success" />
        <span>
          <span className="font-label">{head}</span>
          {" · "}
          {t("mcp.add.test.counts", {
            tools: result.tool_count,
            resources: result.resource_count ?? 0,
            prompts: result.prompt_count ?? 0,
          })}
        </span>
      </p>
      {tools.length > 0 ? (
        <p className="flex flex-wrap gap-1.5">
          {tools.slice(0, SHOWN).map((tool) => (
            <span
              key={tool.name}
              className="rounded-sm border border-border bg-surface px-1.5 py-0.5 font-mono text-2xs text-text-muted"
            >
              {tool.name}
            </span>
          ))}
          {tools.length > SHOWN ? (
            <span className="px-1 py-0.5 text-text-muted">
              {t("mcp.add.test.more", { count: tools.length - SHOWN })}
            </span>
          ) : null}
        </p>
      ) : null}
      {long ? (
        <p className="text-warning">
          {t("mcp.add.test.longName", {
            name: long.name,
            length: `mcp__coffer__${server}__${long.name}`.length,
            limit: NAME_LIMIT,
          })}
        </p>
      ) : null}
      {transport === "http" && !editing ? (
        <p className="text-text-muted">{t("mcp.add.test.allOn", { count: result.tool_count })}</p>
      ) : null}
      {stderr.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <p className="flex items-center gap-2 text-text-muted">
            {t("mcp.add.test.stderrLines", { count: stderr.length })}
            <Button
              variant="link"
              size="sm"
              className="h-auto px-0 text-xs"
              aria-expanded={showStderr}
              onClick={() => setShowStderr((v) => !v)}
            >
              {showStderr ? t("mcp.add.test.hide") : t("mcp.add.test.show")}
            </Button>
          </p>
          {showStderr ? <Stderr lines={stderr} /> : null}
        </div>
      ) : null}
    </div>
  );
}
