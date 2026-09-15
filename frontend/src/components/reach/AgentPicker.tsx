// frontend/src/components/reach/AgentPicker.tsx
//
// The agent list under "only selected agents" in ReachControl's panel — split
// out to keep that file inside its size tier, and because it is one coherent
// job: turn "which agents" into ticks, honestly.
//
// It is a PICK-LIST and never free text: a mistyped name matches nothing, which
// would silently make the resource dormant rather than failing. It offers what
// is registered on this machine, plus any name the stored scope already carries
// that this vault does not recognise — badged, never dropped. Dropping one
// would rewrite the user's scope behind their back, and a scope may legitimately
// name an agent that has not been registered here yet.
//
// It renders under every choice, not only the one it belongs to: under "every
// agent" a tick IS the narrowing (one click from where the user already is),
// and under "Disabled" it is the plainest statement that the selection survived
// the disable and will come back with it.
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { useTranslation } from "react-i18next";

interface Props {
  /** Agents registered on this machine — the pick-list's vocabulary. */
  registered: string[];
  /** The staged selection. */
  selected: string[];
  /** True when this selection currently reaches nobody and the user has chosen
   *  the list — a scope naming nothing, which is NOT the same as disabled. */
  dormant: boolean;
  busy: boolean;
  onToggle: (name: string, checked: boolean) => void;
  className?: string;
}

const WARNING_CLASS =
  "rounded-md border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn";

export function AgentPicker({ registered, selected, dormant, busy, onToggle, className }: Props) {
  const { t } = useTranslation();
  const rows = [...registered, ...selected.filter((name) => !registered.includes(name))];

  return (
    <div className={className} data-testid="scope-agent-axis">
      {dormant ? <p className={WARNING_CLASS}>{t("scope.dormant")}</p> : null}

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("scope.noAgents")}</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((name) => (
            <label
              key={name}
              data-testid={`scope-agent-${name}`}
              className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-border/60 p-2 text-sm"
            >
              <Checkbox
                checked={selected.includes(name)}
                disabled={busy}
                aria-label={name}
                onChange={(e) => onToggle(name, e.target.checked)}
              />
              <span className="min-w-0 flex-1 font-medium">{name}</span>
              {registered.includes(name) ? null : (
                <Badge variant="outline">{t("scope.unknownAgent")}</Badge>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
