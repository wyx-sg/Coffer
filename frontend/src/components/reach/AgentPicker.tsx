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
// It renders under every choice, not only the one it belongs to: under "every
// agent" a tick IS the narrowing (one click from where the user already is),
// and under "Disabled" it is the plainest statement that the selection survived
// the disable and will come back with it.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { WARNING_CLASS, type PickableAgent } from "@/components/reach/reachState";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

interface Props {
  /** Agents registered on this machine — the pick-list's vocabulary. */
  registered: PickableAgent[];
  /** The staged selection, as agent uids. */
  selected: string[];
  /** True when this selection currently reaches nobody and the user has chosen
   *  the list — a scope naming nothing, which is NOT the same as disabled. */
  dormant: boolean;
  busy: boolean;
  onToggle: (uid: string, checked: boolean) => void;
  className?: string;
}

export function AgentPicker({ registered, selected, dormant, busy, onToggle, className }: Props) {
  const { t } = useTranslation();
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

  const stateWord = (agent: (typeof rows)[number]) => {
    if (!agent.known) return t("scope.unknownAgent");
    return agent.installed ? null : t("agentBadge.state.not-installed");
  };

  return (
    <div className={cn("space-y-2", className)} data-testid="scope-agent-axis">
      {dormant ? <p className={WARNING_CLASS}>{t("scope.dormant")}</p> : null}

      {rows.length === 0 ? (
        <p className="px-2 text-xs text-text-muted">{t("scope.noAgents")}</p>
      ) : (
        <div>
          {rows.map((agent) => {
            const word = stateWord(agent);
            return (
              <label
                key={agent.uid}
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
                  disabled={busy}
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
            );
          })}
        </div>
      )}
    </div>
  );
}
