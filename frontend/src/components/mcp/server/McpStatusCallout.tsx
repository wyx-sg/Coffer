// src/components/mcp/server/McpStatusCallout.tsx — the "why, and what next" under the open server's header (design 4.1.01, 4.1.03–4.1.06, 4.1.08).
//
// A failing server's last error, since when, and its last successful call,
// with View log; a missing launcher with the command that installs it; a
// secret this Mac does not hold, with Replace secret; an Off server's
// explanation; many tools behind search. A test the user just ran speaks
// first. Nothing is shown for a healthy server with nothing to say.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { CopyableCommand } from "@/components/settings/CopyableCommand";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/types";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { toneClass } from "@/lib/statusColors";
import { STATUS_TONE, type StatusTone } from "@/components/status/statusTone";
import { cn } from "@/lib/utils";
import { installCommandFor, shortTime, type ServerState } from "./serverState";

type TestResult = components["schemas"]["McpTestResultOut"];

function Callout({
  tone,
  title,
  children,
  action,
  testId,
}: {
  tone: StatusTone;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  testId: string;
}) {
  return (
    <div
      role="status"
      data-testid={testId}
      className={cn(
        "flex flex-col gap-2 rounded-xl px-4 py-3",
        tone === "off" ? "bg-surface-sunken" : toneClass(STATUS_TONE[tone]),
      )}
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-sm font-semibold">{title}</p>
          {children ? <div className="text-xs leading-relaxed text-text">{children}</div> : null}
        </div>
        {action}
      </div>
    </div>
  );
}

interface Props {
  state: ServerState;
  detail: McpStatusDetail | null | undefined;
  tiering: ToolTiering | null | undefined;
  toolCount: number;
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
  const viewLog = (
    <Button size="sm" variant="outline" onClick={onOpenLog}>
      {t("mcp.page.viewLog")}
    </Button>
  );

  if (test) {
    return test.ok ? (
      <Callout
        tone="ok"
        testId="mcp-test-result"
        title={t("mcp.page.testPassed", { ms: test.latency_ms })}
      >
        {t("mcp.page.testPassedBody")}
      </Callout>
    ) : (
      <Callout
        tone="err"
        testId="mcp-test-result"
        title={t("mcp.page.testFailed", { ms: test.latency_ms })}
        action={viewLog}
      >
        {test.error_message}
      </Callout>
    );
  }
  if (state.kind === "off") {
    return (
      <Callout tone="off" testId="mcp-callout-off" title={t("mcp.page.offTitle")}>
        {t("mcp.page.offBody")}
      </Callout>
    );
  }
  if (state.kind === "launcherMissing" && detail?.missing_runner) {
    const install = installCommandFor(detail.missing_runner);
    return (
      <Callout
        tone="warn"
        testId="mcp-callout-launcher"
        title={t("mcp.page.launcherTitle", { runner: detail.missing_runner })}
      >
        <p>{t("mcp.page.launcherBody", { runner: detail.missing_runner, count: toolCount })}</p>
        {install ? (
          <div className="mt-2 max-w-md">
            <CopyableCommand command={install} />
          </div>
        ) : (
          <p className="mt-1">{t("mcp.missingRunnerHint", { runner: detail.missing_runner })}</p>
        )}
      </Callout>
    );
  }
  if (state.kind === "secretMissing") {
    const secret = detail?.missing_secret_ref ?? detail?.missing_secret ?? "";
    return (
      <Callout
        tone="warn"
        testId="mcp-callout-secret"
        title={t("mcp.page.secretTitle", { secret })}
        action={
          <Button size="sm" variant="outline" onClick={onReplaceSecret}>
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
        tone="err"
        testId="mcp-callout-failing"
        title={detail?.last_error ?? t("mcp.page.failingTitle")}
        action={viewLog}
      >
        {facts.length > 0 ? `${facts.join(" · ")}. ` : ""}
        {t("mcp.page.failingBody", { agents: agentNames, count: toolCount })}
        {detail?.last_ok_at
          ? ` ${t("mcp.page.lastSuccess", {
              at: shortTime(detail.last_ok_at),
              tool: detail.last_ok_capability ?? "",
            })}`
          : ""}
      </Callout>
    );
  }
  if (tiering?.enabled && tiering.behind_search.length > 0) {
    const own = tiering.listed.length + tiering.behind_search.length;
    return (
      <Callout
        tone="off"
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
