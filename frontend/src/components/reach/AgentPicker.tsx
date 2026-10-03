// frontend/src/components/reach/AgentPicker.tsx
// The agent checklist of a reach panel (Foundations-Reach "Checklist row" and "Filter").
//
// A "Filter agents" box over a PICK-LIST — never free text: a mistyped name
// matches nothing, which would silently make the resource dormant rather than
// failing. It offers what is registered on this machine, plus any entry the
// stored scope already carries that this vault does not recognise — badged,
// never dropped. Dropping one would rewrite the user's scope behind their back.
//
// A scope stores agent UIDS and a person reads agent NAMES, so ticking writes
// the uid and the label is the name. An unresolved uid prints as itself under
// the "not added here" word, which is the honest answer.
//
// The list is always on screen. It is live only under "Chosen agents"; under
// Off and All agents it sits at 0.45 with every tick kept, which is the plainest
// statement that the selection survives a mode switch.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ReachAgentRow } from "@/components/reach/ReachAgentRow";
import { sortAgents } from "@/components/agent/agentOrder";
import { Input } from "@/components/ui/input";
import { WARNING_CLASS, type PickableAgent, type ReachFailure } from "@/lib/reach/reachState";
import { cn } from "@/lib/utils";

interface Props {
  /** Agents registered on this machine — the pick-list's vocabulary. */
  registered: PickableAgent[];
  /** The staged selection, as agent uids. */
  selected: string[];
  /** True when Chosen agents is picked and nothing is ticked: a scope naming
   *  nobody, which is NOT the same as Off. */
  dormant: boolean;
  /** False dims the list and freezes the ticks (any mode but Chosen agents). */
  active?: boolean;
  /** The failed write, shown on the row it belongs to. */
  failure?: ReachFailure | null;
  busy?: boolean;
  onToggle: (uid: string, checked: boolean) => void;
  /** Re-sends the failed write. */
  onRetry?: () => void;
  className?: string;
}

export function AgentPicker({
  registered,
  selected,
  dormant,
  active = true,
  failure = null,
  busy = false,
  onToggle,
  onRetry,
  className,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const known = new Set(registered.map((a) => a.uid));
  // A stored uid no registered agent answers to still gets a row, labelled with
  // the uid itself: hiding it would display a scope narrower than the one stored.
  const rows: (PickableAgent & { known: boolean })[] = [
    ...sortAgents(registered).map((a) => ({ ...a, known: true })),
    ...selected
      .filter((uid) => !known.has(uid))
      .map((uid) => ({ uid, name: uid, type: "", installed: true, known: false })),
  ];
  const needle = query.trim().toLowerCase();
  const shown = needle ? rows.filter((a) => a.name.toLowerCase().includes(needle)) : rows;

  return (
    <div className={cn("flex min-h-0 flex-col gap-2", className)} data-testid="scope-agent-axis">
      {dormant ? <p className={WARNING_CLASS}>{t("scope.dormant")}</p> : null}
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("scope.filterAgents")}
        aria-label={t("scope.filterAgents")}
        className="h-[30px] shrink-0 text-sm"
      />
      <div className={cn("min-h-0 overflow-y-auto", !active && "opacity-[.45]")}>
        {rows.length === 0 ? (
          <p className="px-2 text-xs text-text-muted">{t("scope.noAgents")}</p>
        ) : shown.length === 0 ? (
          <p className="px-2 text-xs text-text-muted">{t("scope.noMatch")}</p>
        ) : (
          shown.map((agent) => (
            <ReachAgentRow
              key={agent.uid}
              agent={agent}
              checked={selected.includes(agent.uid)}
              disabled={busy || !active}
              failure={failure?.uid === agent.uid ? failure : null}
              onToggle={onToggle}
              onRetry={onRetry}
            />
          ))
        )}
      </div>
    </div>
  );
}
