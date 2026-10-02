// src/components/agents/AgentHooksByEvent.tsx — the Hooks tab's body: the agent's hooks grouped by event.
//
// Spec agent-registry "List every hook in the agent's native config". One block
// per event the agent fires (SessionStart, PreToolUse, …), each listing the
// hooks that run on it — the command, the matcher it applies to and the file
// that declares it. Coffer's memory hook sits on several events with one
// command, so it appears under each of them, marked "Coffer"; its health (missing,
// out of date, awaiting approval, never fired) is said once, in the status block
// above the events, with Repair — not repeated per event. Nothing here opens a
// file: hooks are changed in their own files.
import { useTranslation } from "react-i18next";
import { Wrench } from "lucide-react";

import { AgentHookCommandCell } from "@/components/agents/AgentHookCommandCell";
import { AgentHookStateCell } from "@/components/agents/AgentHookStateCell";
import { Section, SectionStack } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import { cofferHookState, fileName, type HookRow } from "@/lib/agents/hookRows";

/** The order the agents fire them in; any other event follows, alphabetically. */
const EVENT_ORDER = [
  "SessionStart",
  "UserPromptSubmit",
  "PreToolUse",
  "PostToolUse",
  "Notification",
  "Stop",
  "SubagentStop",
  "PreCompact",
  "SessionEnd",
];

function rank(event: string): number {
  const i = EVENT_ORDER.indexOf(event);
  return i === -1 ? EVENT_ORDER.length : i;
}

/** Rows regrouped by event: a row naming several events (Coffer's) lands under each. */
function byEvent(rows: readonly HookRow[]): [string, HookRow[]][] {
  const map = new Map<string, HookRow[]>();
  for (const row of rows) {
    if (row.command === null) continue; // a missing hook has no command to list
    for (const event of row.events) map.set(event, [...(map.get(event) ?? []), row]);
  }
  return [...map.entries()].sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
}

interface Props {
  /** The rows left after the owner filter and search. */
  rows: readonly HookRow[];
  /** Coffer's own hook row, whether or not the filters hide it: its status is always said. */
  cofferRow: HookRow | null;
  agentType: string;
  onRepair?: () => void;
  onCheckAgain: () => void;
  checking: boolean;
}

function CofferStatus({
  row,
  agentType,
  onRepair,
  onCheckAgain,
  checking,
}: Omit<Props, "rows" | "cofferRow"> & { row: HookRow }) {
  const { t } = useTranslation();
  const state = row.coffer ? cofferHookState(row.coffer) : null;
  if (!state || state.word === "current") return null;
  return (
    <div
      className="flex items-start gap-4 rounded-lg border border-border bg-surface-raised px-4 py-3"
      data-testid="coffer-hook-status"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="text-sm font-medium text-text">{t("agents.hooksTab.cofferHook")}</span>
        <AgentHookCommandCell
          row={row}
          agentType={agentType}
          onCheckAgain={onCheckAgain}
          checking={checking}
        />
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <AgentHookStateCell row={row} />
        {state.repair && onRepair ? (
          <Button variant="outline" size="sm" onClick={onRepair}>
            <Wrench aria-hidden /> {t("agents.hooksTab.repair")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function AgentHooksByEvent({ rows, cofferRow, ...rest }: Props) {
  const { t } = useTranslation();
  const groups = byEvent(rows);
  return (
    <div className="flex flex-col gap-5">
      {cofferRow ? <CofferStatus row={cofferRow} {...rest} /> : null}
      {groups.length === 0 ? (
        <p className="text-sm text-text-muted">{t("agents.hooksTab.noMatches")}</p>
      ) : (
        <SectionStack>
          {groups.map(([event, hooks]) => (
            <Section key={event} title={event} gap="snug" testId={`hook-event-${event}`}>
              <ul className="flex flex-col divide-y divide-border-subtle">
                {hooks.map((row) => (
                  <li key={row.key} className="flex items-start gap-3 py-2 first:pt-0">
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <TruncatedText mono text={row.command ?? ""} className="text-xs text-text" />
                      <TruncatedText
                        className="text-xs text-text-muted"
                        text={[
                          t("agents.hooksTab.matcher", {
                            matcher: row.matcher || t("agents.hooksTab.matcherAny"),
                          }),
                          row.plugin
                            ? `${row.plugin.split("@")[0]} · ${fileName(row.path)}`
                            : abbreviateHomePath(row.path),
                        ].join(" · ")}
                      />
                    </span>
                    {row.owner === "coffer" ? (
                      <Badge variant="outline" className="shrink-0">
                        Coffer
                      </Badge>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>
          ))}
        </SectionStack>
      )}
    </div>
  );
}
