// frontend/src/components/ScopeCard.tsx
//
// ScopeCard: the resource-detail-page editor for a Kind's machine x agent
// activation scope (ADR-045). GET/PUT /resources/{kind}/{name}/scope (Task 16's
// useResourceScope/useUpdateResourceScope) backs this; useMachines() supplies
// the synced-machine registry to render rows for, and useAgents() supplies the
// registered-agent list for dual-axis kinds' (axes includes "agent") per-row
// agent multi-select. Machine-only kinds (agent, channel) render a bare on/off
// per machine — the scope value is always "*" (see backend/coffer/domain/
// scope.py validate_scope, which rejects list values on machine-only axes).
//
// Mutation pattern: immediate PUT per change, no local staging + explicit
// Save button — matching ChannelMachineCard (Task 13's scope-backed rebind
// control) rather than SyncSettings' save-button flow. Every control in this
// card already represents a complete, valid scope value on its own, so there
// is nothing to batch:
//   - Everywhere -> Custom writes `{}` — "custom, no entries" is itself a
//     well-defined, already-rendered state (the dormant warning below), so
//     the header switch is an honest mutation rather than local-only UI state
//     that silently diverges from the server until some later action.
//   - Custom -> Everywhere writes `null`.
//   - A row's on/off switch writes `"*"` (on) or removes the entry (off).
//     Dual-axis kinds default a freshly-on row to `"*"` (all agents) so the
//     row is immediately meaningful without a second interaction.
//   - The "all agents" checkbox writes `"*"` (checked) or `[]` (unchecked).
//   - Per-agent checkboxes add/remove that agent from the row's list.
import { Globe2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAgents } from "@/lib/hooks/useAgents";
import { useMachines } from "@/lib/hooks/useMachines";
import { useResourceScope, useUpdateResourceScope, type Scope } from "@/lib/hooks/useScope";
import {
  ScopeMachineRow,
  WILDCARD,
  type ScopeMachineRowData,
} from "@/components/scope/ScopeMachineRow";

type Row = ScopeMachineRowData;

export function ScopeCard({ kind, name }: { kind: string; name: string }) {
  const { t } = useTranslation();
  const { data: scopeData } = useResourceScope(kind, name);
  const { data: machinesData } = useMachines();
  const { data: agentsData } = useAgents();
  const update = useUpdateResourceScope(kind, name);

  const axes = scopeData?.axes ?? [];
  const dualAxis = axes.includes("agent");
  const scope = scopeData?.scope ?? null;
  const isCustom = scope !== null;
  const machines = machinesData?.machines ?? [];
  const agents = agentsData ?? [];

  const rows: Row[] = [
    ...machines.map((m) => ({
      id: m.machine_id,
      displayName: m.display_name,
      isLocal: m.is_local,
      isKnown: true,
    })),
    ...Object.keys(scope ?? {})
      .filter((id) => !machines.some((m) => m.machine_id === id))
      .map((id) => ({ id, displayName: id, isLocal: false, isKnown: false })),
  ];

  const localMachine = machines.find((m) => m.is_local);
  const activeHere = (() => {
    if (!isCustom) return true;
    if (!localMachine) return false;
    const value = scope?.[localMachine.machine_id];
    if (value === undefined) return false;
    if (value === WILDCARD) return true;
    return value.length > 0;
  })();

  const setRowValue = (id: string, value: Scope[string] | null) => {
    const next = { ...(scope ?? {}) };
    if (value === null) delete next[id];
    else next[id] = value;
    update.mutate(next);
  };

  return (
    <Card className="paper-card" data-testid="scope-card">
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle className="flex items-center gap-2 font-serif text-lg">
          <Globe2 className="size-4 text-primary" aria-hidden />
          {t("scope.title")}
        </CardTitle>
        <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
          <Button
            type="button"
            size="sm"
            variant={isCustom ? "ghost" : "secondary"}
            disabled={update.isPending || !isCustom}
            onClick={() => update.mutate(null)}
          >
            {t("scope.everywhere")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={isCustom ? "secondary" : "ghost"}
            disabled={update.isPending || isCustom}
            onClick={() =>
              update.mutate(
                machines.length === 0
                  ? {}
                  : Object.fromEntries(machines.map((m) => [m.machine_id, WILDCARD])),
              )
            }
          >
            {t("scope.custom")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>

        {isCustom ? (
          <>
            {Object.keys(scope ?? {}).length === 0 ? (
              <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-400">
                {t("scope.dormant")}
              </p>
            ) : null}

            {!activeHere ? (
              <p className="text-xs text-muted-foreground">{t("scope.notActiveHere")}</p>
            ) : null}

            {rows.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("scope.noMachines")}</p>
            ) : (
              <div className="space-y-2">
                {rows.map((row) => (
                  <ScopeMachineRow
                    key={row.id}
                    row={row}
                    value={scope?.[row.id]}
                    dualAxis={dualAxis}
                    agents={agents.map((a) => a.name)}
                    disabled={update.isPending}
                    onToggle={(on) => setRowValue(row.id, on ? WILDCARD : null)}
                    onAllAgentsChange={(all) => setRowValue(row.id, all ? WILDCARD : [])}
                    onAgentToggle={(agentName, checked) => {
                      const current = scope?.[row.id];
                      const list = Array.isArray(current) ? current : [];
                      const next = checked
                        ? [...list, agentName]
                        : list.filter((a) => a !== agentName);
                      setRowValue(row.id, next);
                    }}
                  />
                ))}
              </div>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
