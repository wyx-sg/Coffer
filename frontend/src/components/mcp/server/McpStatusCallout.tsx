// src/components/mcp/server/McpStatusCallout.tsx — the "why, and what next" at the top of the open server's Overview (design 4.1.04–4.1.07).
//
// The fix for a problem lives here, never in the header: an Off server's
// Turn on; a secret this Mac does not hold, Add secret (the Secrets page's own
// dialog for that name); a missing launcher, the install hand-off; a failing
// server's last error, since when, who can't call it and its last successful
// call, with View log (stdio) or View errors (HTTP: the Activity page on its
// failed calls) and the diagnosis hand-off; a rejected key, with Replace key (the
// edit dialog on its secret). A test the user just ran speaks here only when
// it failed (a pass is a toast). Nothing for a healthy server.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, KeyRound, Power, SquareTerminal, TriangleAlert } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button, type ButtonProps } from "@/components/ui/button";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { McpCallout as Callout } from "./McpCallout";
import { seconds, shortDate, shortTime, type ServerState } from "@/lib/mcp/serverState";
import type { TestResult } from "./testResult";

/** A clause that opens the sentence starts with a capital. */
const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** A callout's own action with the backend's hand-off beside it, when it has one. */
function withHandoff(action: ReactNode, prompt: string | undefined) {
  if (!prompt) return action;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {action}
      <AgentHandoff prompt={prompt} size="sm" />
    </div>
  );
}

/** A callout's action button: small, outline, on the raised surface. */
function CalloutButton(props: ButtonProps) {
  return <Button size="sm" variant="outline" className="bg-surface-raised" {...props} />;
}

interface Props {
  name: string;
  state: ServerState;
  detail: McpStatusDetail | null | undefined;
  /** Streamable HTTP: no log of its own, so a failure offers View errors. */
  isHttp: boolean;
  toolCount: number;
  /** The agents that reach it, already worded ("Claude Code and Codex"); "" when none. */
  agentNames: string;
  /** Who turning it on gives it to: `null` is every agent, "" none registered here. */
  turnOnNames: string | null;
  /** A failed test the user just ran; a passed one is a toast, not shown here. */
  test: TestResult | null;
  onOpenLog: () => void;
  onViewErrors: () => void;
  onTurnOn: () => void;
  onAddSecret: () => void;
  onReplaceKey: () => void;
}

export function McpStatusCallout({
  name,
  state,
  detail,
  isHttp,
  toolCount,
  agentNames,
  turnOnNames,
  test,
  onOpenLog,
  onViewErrors,
  onTurnOn,
  onAddSecret,
  onReplaceKey,
}: Props) {
  const { t } = useTranslation();
  const [stderr, setStderr] = useState(false);
  const viewLog = (
    <CalloutButton onClick={isHttp ? onViewErrors : onOpenLog}>
      <SquareTerminal aria-hidden /> {t(isHttp ? "mcp.page.viewErrors" : "mcp.page.viewLog")}
    </CalloutButton>
  );
  const tools =
    toolCount > 0 ? t("mcp.page.itsTools", { count: toolCount }) : t("mcp.page.itsToolsAny");
  const who = agentNames || t("mcp.page.agentsSubject");

  if (test && !test.ok) {
    const lines = test.stderr_tail ?? [];
    const stderrButton =
      lines.length > 0 ? (
        <CalloutButton aria-expanded={stderr} onClick={() => setStderr((v) => !v)}>
          <SquareTerminal aria-hidden />
          {stderr ? t("mcp.page.hideStderr") : t("mcp.page.showStderr")}
        </CalloutButton>
      ) : (
        viewLog
      );
    return (
      <Callout
        tint="err"
        icon={CircleAlert}
        testId="mcp-test-result"
        title={t("mcp.page.testFailed", { took: seconds(test.latency_ms) })}
        action={withHandoff(stderrButton, test.handoff?.prompt)}
      >
        {test.error_message}
        {stderr && lines.length > 0 ? (
          <pre
            className="mt-2 max-h-40 overflow-auto rounded-md bg-surface-raised p-2 font-mono text-2xs"
            data-testid="mcp-test-stderr"
          >
            {lines.join("\n")}
          </pre>
        ) : null}
      </Callout>
    );
  }
  if (state.kind === "off") {
    return (
      <Callout
        tint="off"
        icon={Power}
        testId="mcp-callout-off"
        title={t("mcp.page.offTitle")}
        action={
          <CalloutButton onClick={onTurnOn}>
            <Power aria-hidden /> {t("mcp.page.turnOn")}
          </CalloutButton>
        }
      >
        {turnOnNames === null
          ? t("mcp.page.offBodyEveryone")
          : turnOnNames
            ? t("mcp.page.offBodyAgents", { agents: turnOnNames })
            : t("mcp.page.offBody")}
      </Callout>
    );
  }
  if (state.kind === "launcherMissing" && detail?.missing_runner) {
    const runner = detail.missing_runner;
    return (
      <Callout
        tint="warn"
        icon={TriangleAlert}
        testId="mcp-callout-launcher"
        title={t("mcp.page.launcherTitle", { runner })}
        action={withHandoff(null, detail.handoff?.prompt)}
      >
        {t("mcp.page.launcherBodyWho", { name, runner, who, tools })}
      </Callout>
    );
  }
  if (state.kind === "secretMissing") {
    const key = detail?.missing_secret ?? "";
    return (
      <Callout
        tint="warn"
        icon={KeyRound}
        testId="mcp-callout-secret"
        title={t("mcp.page.secretTitle", { key })}
        action={
          <CalloutButton onClick={onAddSecret}>
            <KeyRound aria-hidden /> {t("mcp.page.addSecret")}
          </CalloutButton>
        }
      >
        {detail?.last_ok_at
          ? t("mcp.page.secretBodyWorked", { at: shortDate(detail.last_ok_at) })
          : t("mcp.page.secretBody")}
      </Callout>
    );
  }
  if (state.kind === "failing" && detail?.failure_reason === "auth_rejected") {
    return (
      <Callout
        tint="err"
        icon={KeyRound}
        testId="mcp-callout-key-rejected"
        title={t("mcp.page.keyRejectedTitle")}
        action={withHandoff(
          <CalloutButton onClick={onReplaceKey}>{t("mcp.page.replaceKey")}</CalloutButton>,
          detail.handoff?.prompt,
        )}
      >
        {t("mcp.page.keyRejectedBody", { who, tools })}
      </Callout>
    );
  }
  if (state.kind === "failing") {
    const facts: string[] = [];
    if (detail?.last_error_at)
      facts.push(t("mcp.page.lastErrorAt", { at: shortTime(detail.last_error_at) }));
    if (detail?.failing_since)
      facts.push(t("mcp.page.failingSince", { at: shortTime(detail.failing_since) }));
    return (
      <Callout
        tint="err"
        icon={CircleAlert}
        testId="mcp-callout-failing"
        title={detail?.last_error ?? t("mcp.page.failingTitle")}
        action={withHandoff(viewLog, detail?.handoff?.prompt)}
      >
        {facts.length > 0 ? `${sentence(facts.join(" · "))}. ` : ""}
        {t("mcp.page.failingBodyWho", { who, tools })}
        {detail?.last_ok_at
          ? ` ${
              detail.last_ok_capability
                ? t("mcp.page.lastSuccess", {
                    at: shortTime(detail.last_ok_at),
                    tool: detail.last_ok_capability,
                  })
                : t("mcp.page.lastSuccessAt", { at: shortTime(detail.last_ok_at) })
            }`
          : ""}
      </Callout>
    );
  }
  return null;
}
