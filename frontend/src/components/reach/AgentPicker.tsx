// frontend/src/components/reach/AgentPicker.tsx
// The agent checklist of ReachControl's panel (Foundations-Reach "Checklist row").
//
// The agent list under "only selected agents" in ReachControl's panel — split
// out to keep that file inside its size tier, and because it is one coherent
// job: turn "which agents" into ticks, honestly.
//
// It is a PICK-LIST and never free text: a mistyped name matches nothing, which
// would silently make the resource dormant rather than failing. It offers what
// is registered on this machine, plus any entry the stored scope already carries
// that this vault does not recognise — badged, never dropped. Dropping one
// would rewrite the user's scope behind their back, and a scope may legitimately
// name an agent that has not been registered here yet.
//
// A scope stores agent UIDS and a person reads agent NAMES, so this list holds
// both: `registered` carries the pair, ticking writes the uid, and the label is
// the name. An unresolved uid has no name to print, so it prints as itself
// under the "unknown agent" badge — which is the honest answer, and the only
// one that does not quietly widen the scope by leaving it out.
//
// It renders under every mode, not only the one it belongs to: while the mode is
// not "Chosen agents" the list is shown at 0.45 and disabled, which is the
// plainest statement that the ticks survive and come back with the mode.
//
// A "Filter agents" box narrows the visible rows by name; ticks on hidden rows
// are untouched. A row whose write failed shows "Failed", the reason and a
// Retry in place of its state word — the failure belongs to that agent, so it
// is said there, not in a toast.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import type { PickableAgent } from "@/lib/reach/reachState";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface RowFailure {
  uid: string;
  message: string;
  onRetry: () => void;
}

interface Props {
  /** Agents registered on this machine — the pick-list's vocabulary. */
  registered: PickableAgent[];
  /** The staged selection, as agent uids. */
  selected: string[];
  /** Uids ticked on SOME of a bulk selection's rows: drawn as a dash, and a
   *  click makes them ticked for all. */
  partial?: string[];
  /** The mode is not "Chosen agents": 0.45 opacity, every tick inert, ticks kept. */
  inactive?: boolean;
  busy?: boolean;
  failure?: RowFailure | null;
  onToggle: (uid: string, checked: boolean) => void;
  className?: string;
}

export function AgentPicker({
  registered,
  selected,
  partial = [],
  inactive = false,
  busy = false,
  failure = null,
  onToggle,
  className,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const known = new Set(registered.map((a) => a.uid));
  // A stored uid no registered agent answers to still gets a row, labelled with
  // the uid itself: there is no name to show, and hiding the row would display
  // a scope narrower than the one stored.
  const rows: (PickableAgent & { known: boolean })[] = [
    ...sortAgents(registered).map((a) => ({ ...a, known: true })),
    ...selected
      .filter((uid) => !known.has(uid))
      .map((uid) => ({ uid, name: uid, type: "", installed: true, known: false })),
  ];

  const needle = query.trim().toLowerCase();
  const visible = needle ? rows.filter((a) => a.name.toLowerCase().includes(needle)) : rows;

  const stateWord = (agent: (typeof rows)[number]) => {
    if (!agent.known) return t("scope.unknownAgent");
    return agent.installed ? null : t("agentBadge.state.not-installed");
  };

  return (
    <div className={cn("space-y-2", className)} data-testid="scope-agent-axis">
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("scope.filterAgents")}
        aria-label={t("scope.filterAgents")}
        className="h-control-sm text-xs"
      />

      {rows.length === 0 ? (
        <p className="px-2 text-xs text-text-muted">{t("scope.noAgents")}</p>
      ) : (
        <div
          data-testid="scope-agent-list"
          aria-disabled={inactive || undefined}
          className={cn(inactive && "opacity-45")}
        >
          {visible.map((agent) => {
            const word = stateWord(agent);
            const failed = failure?.uid === agent.uid ? failure : null;
            return (
              <div key={agent.uid}>
                <label
                  // React keys on the identity; the test id stays the NAME, as it
                  // always was, because that is what a test (and a reader of the
                  // DOM) recognises a row by and a uid would make every such
                  // assertion unreadable. An unresolved uid labels its own row, so
                  // the attribute is still unique either way.
                  data-testid={`scope-agent-${agent.name}`}
                  className="flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-item px-2 transition-colors duration-fast hover:bg-surface-hover"
                >
                  <Checkbox
                    checked={selected.includes(agent.uid)}
                    indeterminate={!selected.includes(agent.uid) && partial.includes(agent.uid)}
                    disabled={busy || inactive}
                    aria-label={agent.name}
                    onChange={(e) => onToggle(agent.uid, e.target.checked)}
                  />
                  {/* The name beside it is the visible text, so the badge is
                    decoration here — the checkbox is already named. */}
                  <span aria-hidden className="inline-flex">
                    <AgentBadge
                      type={agent.type}
                      name={agent.name}
                      size="md"
                      tooltip={false}
                      state={agent.installed ? undefined : "not-installed"}
                    />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-normal text-text">
                    {agent.name}
                  </span>
                  {word ? <span className="shrink-0 text-xs text-text-muted">{word}</span> : null}
                </label>
                {failed ? (
                  <p
                    role="alert"
                    data-testid="scope-agent-failed"
                    className="flex items-center gap-1.5 px-2 pb-1 pl-[39px] text-xs text-danger"
                  >
                    <span className="min-w-0 flex-1">
                      {t("scope.rowFailed")} — {failed.message}
                    </span>
                    <button
                      type="button"
                      className="shrink-0 font-label underline"
                      onClick={failed.onRetry}
                    >
                      {t("common.retry")}
                    </button>
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
