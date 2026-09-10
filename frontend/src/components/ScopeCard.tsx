// frontend/src/components/ScopeCard.tsx
//
// ScopeCard: the resource-detail-page editor for a kind's per-agent activation
// scope (ADR per-agent-resource-scope). GET/PUT /resources/{kind}/{name}/scope
// (useResourceScope/useUpdateResourceScope) backs this; useAgents() supplies
// the registered-agent list. Only `mcp_server` and `skill` support scope — the
// card renders nothing for kinds that don't, so their detail pages don't have
// to know.
//
// The value is a single axis: a list of agent names.
//   null  → active for every agent ("Every agent")
//   []    → active for no agent (dormant)
//   [...] → active only for the named agents
//
// Mutation pattern: immediate PUT per change, no local staging + Save button.
// Every control already represents a complete, valid scope value on its own:
//   - "Every agent" writes `null`.
//   - "Selected agents" writes `[]` — "selected, nothing selected yet" is
//     itself a well-defined state (the dormant warning below), so the switch is
//     an honest mutation rather than local-only UI state that silently diverges
//     from the server until some later action.
//   - A checkbox adds/removes that agent from the list.
// An agent name in the list that isn't registered here is legal (a resource can
// be scoped in before the agent exists), so it renders as an extra row.
import { Globe2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { useAgents } from "@/lib/hooks/useAgents";
import { useResourceScope, useUpdateResourceScope } from "@/lib/hooks/useScope";

export function ScopeCard({ kind, name }: { kind: string; name: string }) {
  const { t } = useTranslation();
  const { data: scopeData } = useResourceScope(kind, name);
  const { data: agentsData } = useAgents();
  const update = useUpdateResourceScope(kind, name);

  // Kinds that declare no scope (agent, channel, knowledge_base, memory) get
  // no editor at all.
  if (scopeData && !scopeData.supports_scope) return null;

  const scope = scopeData?.scope ?? null;
  const isCustom = scope !== null;
  const registered = (agentsData ?? []).map((a) => a.name);
  const unknown = (scope ?? []).filter((n) => !registered.includes(n));
  const rows = [
    ...registered.map((n) => ({ name: n, known: true })),
    ...unknown.map((n) => ({ name: n, known: false })),
  ];

  const toggleAgent = (agentName: string, checked: boolean) => {
    const list = scope ?? [];
    update.mutate(checked ? [...list, agentName] : list.filter((a) => a !== agentName));
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
            {t("scope.everyAgent")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={isCustom ? "secondary" : "ghost"}
            disabled={update.isPending || isCustom}
            onClick={() => update.mutate([])}
          >
            {t("scope.selectedAgents")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>

        {isCustom ? (
          <>
            {scope.length === 0 ? (
              <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-400">
                {t("scope.dormant")}
              </p>
            ) : null}

            {rows.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("scope.noAgents")}</p>
            ) : (
              <div className="space-y-2">
                {rows.map((row) => (
                  <label
                    key={row.name}
                    data-testid={`scope-agent-${row.name}`}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-border/60 p-2.5 text-sm"
                  >
                    <Checkbox
                      checked={scope.includes(row.name)}
                      disabled={update.isPending}
                      aria-label={row.name}
                      onChange={(e) => toggleAgent(row.name, e.target.checked)}
                    />
                    <span className="font-medium">{row.name}</span>
                    {!row.known ? <Badge variant="outline">{t("scope.unknownAgent")}</Badge> : null}
                  </label>
                ))}
              </div>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
