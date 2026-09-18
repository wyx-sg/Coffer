// frontend/src/components/reach/AgentPicker.tsx
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
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { useTranslation } from "react-i18next";

/** One agent the list can offer: what a tick WRITES, and what it READS as. */
interface PickableAgent {
  uid: string;
  name: string;
}

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

const WARNING_CLASS =
  "rounded-md border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn";

export function AgentPicker({ registered, selected, dormant, busy, onToggle, className }: Props) {
  const { t } = useTranslation();
  const known = new Set(registered.map((a) => a.uid));
  // A stored uid no registered agent answers to still gets a row, labelled with
  // the uid itself: there is no name to show, and hiding the row would display
  // a scope narrower than the one stored.
  const rows: (PickableAgent & { known: boolean })[] = [
    ...registered.map((a) => ({ ...a, known: true })),
    ...selected.filter((uid) => !known.has(uid)).map((uid) => ({ uid, name: uid, known: false })),
  ];

  return (
    <div className={className} data-testid="scope-agent-axis">
      {dormant ? <p className={WARNING_CLASS}>{t("scope.dormant")}</p> : null}

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("scope.noAgents")}</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((agent) => (
            <label
              key={agent.uid}
              // React keys on the identity; the test id stays the NAME, as it
              // always was, because that is what a test (and a reader of the
              // DOM) recognises a row by and a uid would make every such
              // assertion unreadable. An unresolved uid labels its own row, so
              // the attribute is still unique either way.
              data-testid={`scope-agent-${agent.name}`}
              className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-border/60 p-2 text-sm"
            >
              <Checkbox
                checked={selected.includes(agent.uid)}
                disabled={busy}
                aria-label={agent.name}
                onChange={(e) => onToggle(agent.uid, e.target.checked)}
              />
              <span className="min-w-0 flex-1 font-medium">{agent.name}</span>
              {agent.known ? null : <Badge variant="outline">{t("scope.unknownAgent")}</Badge>}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
