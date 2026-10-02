// src/components/mcp/server/McpStatusCallout.tsx — the "why, and what next" at the top of the open server's Overview (design 4.1.01–4.1.06).
//
// A test the user just ran speaks first (passed: what it listed; failed: why,
// with its stderr one click away and the diagnosis hand-off beside it).
// Otherwise the state's own callout: a failing server's last error, since
// when, who can't call it and its last successful call, with View log and the
// diagnosis hand-off; a missing launcher, with the install hand-off (the
// backend's prompt — which installer fits is the agent's call, so no install
// command is named here); a secret this Mac does not hold, with Replace
// secret; an Off server's explanation; many tools behind search. Nothing for
// a healthy server with nothing to say.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  CircleAlert,
  KeyRound,
  Layers,
  Power,
  SquareTerminal,
  TriangleAlert,
} from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { McpCallout as Callout } from "./McpCallout";
import { seconds, shortTime, type ServerState, secretLabel } from "@/lib/mcp/serverState";
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

interface Props {
  state: ServerState;
  detail: McpStatusDetail | null | undefined;
  tiering: ToolTiering | null | undefined;
  toolCount: number;
  /** The agents that reach it, already worded ("Claude Code and Codex"); "" when none. */
  agentNames: string;
  test: TestResult | null;
  onOpenLog: () => void;
  onReplaceSecret: () => void;
}

export function McpStatusCallout({
  state,
  detail,
  tiering,
  toolCount,
  agentNames,
  test,
  onOpenLog,
  onReplaceSecret,
}: Props) {
  const { t } = useTranslation();
  const [stderr, setStderr] = useState(false);
  const viewLog = (
    <Button size="sm" variant="outline" className="bg-surface-raised" onClick={onOpenLog}>
      <SquareTerminal aria-hidden /> {t("mcp.page.viewLog")}
    </Button>
  );
  const tools =
    toolCount > 0 ? t("mcp.page.itsTools", { count: toolCount }) : t("mcp.page.itsToolsAny");
  const who = agentNames || t("mcp.page.agentsSubject");

  if (test) {
    const lines = test.stderr_tail ?? [];
    const stderrButton =
      lines.length > 0 ? (
        <Button
          size="sm"
          variant="outline"
          className="bg-surface-raised"
          aria-expanded={stderr}
          onClick={() => setStderr((v) => !v)}
        >
          <SquareTerminal aria-hidden />
          {stderr ? t("mcp.page.hideStderr") : t("mcp.page.showStderr")}
        </Button>
      ) : test.ok ? null : (
        viewLog
      );
    const tail =
      stderr && lines.length > 0 ? (
        <pre
          className="mt-2 max-h-40 overflow-auto rounded-md bg-surface-raised p-2 font-mono text-2xs"
          data-testid="mcp-test-stderr"
        >
          {lines.join("\n")}
        </pre>
      ) : null;
    const took = seconds(test.latency_ms);
    if (test.ok) {
      const exit = test.exit_code != null ? t("mcp.page.testExit", { code: test.exit_code }) : "";
      return (
        <Callout
          tint="ok"
          icon={Check}
          testId="mcp-test-result"
          title={`${t("mcp.page.testPassed", { took })}${exit}`}
          action={stderrButton}
        >
          {test.tool_count !== undefined
            ? t("mcp.page.testListed", {
                tools: test.tool_count,
                resources: test.resource_count ?? 0,
                prompts: test.prompt_count ?? 0,
              })
            : t("mcp.page.testPassedBody")}
          {tail}
        </Callout>
      );
    }
    return (
      <Callout
        tint="err"
        icon={CircleAlert}
        testId="mcp-test-result"
        title={t("mcp.page.testFailed", { took })}
        action={withHandoff(stderrButton, test.handoff?.prompt)}
      >
        {test.error_message}
        {tail}
      </Callout>
    );
  }
  if (state.kind === "off") {
    return (
      <Callout tint="off" icon={Power} testId="mcp-callout-off" title={t("mcp.page.offTitle")}>
        {agentNames ? t("mcp.page.offBodyAgents", { agents: agentNames }) : t("mcp.page.offBody")}
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
        {t("mcp.page.launcherBodyWho", { runner, who, tools })}
      </Callout>
    );
  }
  if (state.kind === "secretMissing") {
    const secret = detail?.missing_secret_ref
      ? secretLabel(detail.missing_secret_ref)
      : (detail?.missing_secret ?? "");
    return (
      <Callout
        tint="warn"
        icon={KeyRound}
        testId="mcp-callout-secret"
        title={t("mcp.page.secretTitle", { secret })}
        action={
          <Button
            size="sm"
            variant="outline"
            className="bg-surface-raised"
            onClick={onReplaceSecret}
          >
            {t("mcp.page.replaceSecret")}
          </Button>
        }
      >
        {t("mcp.page.secretBody", { key: detail?.missing_secret ?? "" })}
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
  if (tiering?.enabled && tiering.behind_search.length > 0) {
    const own = tiering.listed.length + tiering.behind_search.length;
    return (
      <Callout
        tint="info"
        icon={Layers}
        testId="mcp-callout-tiering"
        title={t("mcp.page.tieringTitle", {
          listed: tiering.listed.length,
          total: own,
          behind: tiering.behind_search.length,
        })}
      >
        {t("mcp.page.tieringBody", {
          catalogue: tiering.catalogue_size,
          budget: tiering.listed_count,
        })}
      </Callout>
    );
  }
  return null;
}
