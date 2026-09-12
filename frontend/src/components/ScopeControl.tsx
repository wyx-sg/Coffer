// frontend/src/components/ScopeControl.tsx
//
// ScopeControl: the single control that answers "who does this resource
// reach?" — it owns both the resource's `enabled` flag and its per-agent
// activation scope (ADR per-agent-resource-scope). It replaces the old pair of controls (an enable
// Switch in the page header + a separate "Activation scope" card further down),
// which expressed the same "reaches nobody" state twice: `enabled=false` in one
// place and `scope=[]` (the dormant warning) in another.
//
// Data: GET/PUT /resources/{kind}/{name}/scope (useResourceScope /
// useUpdateResourceScope) plus POST .../enable|disable
// (useEnableResource/useDisableResource); useAgents() supplies the registered
// agent list.
//
// The scope value is a single axis: a list of agent names.
//   null  → active for every agent ("Every agent")
//   []    → active for no agent (dormant)
//   [...] → active only for the named agents
// Layered on top of it, the resource's own `enabled` flag is the control's
// first state: disabled beats any scope. Disabling deliberately LEAVES the
// scope untouched, so re-enabling restores the agent selection the user had.
//
// Mutation pattern (unchanged): immediate PUT/POST per change, no local
// staging + Save button. Every control already represents a complete, valid
// value on its own:
//   - "Disabled" posts .../disable and writes no scope.
//   - "Every agent" enables if needed and writes `null`.
//   - "Selected agents" enables if needed, writes `[]` when the scope was
//     `null` ("selected, nothing selected yet" is itself a well-defined state —
//     the dormant warning in the popover), and opens the agent list.
//   - A checkbox adds/removes that agent from the list.
// An agent name in the list that isn't registered here is legal (a resource can
// be scoped in before the agent exists), so it renders as an extra row.
//
// Kinds that declare no scope (agent, channel, knowledge_base, memory) still
// need enable/disable — this control now owns it — so they fall back to a
// two-segment Disabled/Enabled group.
//
// The control also sits in the status column of the skills and MCP-servers
// LISTS, one instance per row, because a resource's reach is no longer a plain
// on/off the user can read off a Switch. Mounting the per-resource scope query
// once per row would turn one list render into one GET per row, so the list
// callers pass `scope` straight from the payload they already fetched
// (`SkillOut.scope` / `ResourceOut.scope`) and the query stays off: the list
// costs zero extra requests. Passing `scope` also asserts "this kind supports
// scope", which is true of the only two kinds whose lists mount it. The detail
// pages pass nothing and keep fetching, since they render one resource.
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import {
  useResourceScope,
  useUpdateResourceScope,
  type ResourceScope,
  type Scope,
} from "@/lib/hooks/useScope";

const GROUP_CLASS = "flex items-center gap-1 rounded-md border border-border p-0.5";

interface Props {
  kind: string;
  name: string;
  enabled: boolean;
  /** Pre-fetched scope from a list payload (`null` = every agent). Omit it to
   *  let the control fetch its own; `undefined` is "not supplied", never a
   *  value. */
  scope?: Scope | null;
}

export function ScopeControl({ kind, name, enabled, scope: presetScope }: Props) {
  const { t } = useTranslation();
  const prefetched = presetScope !== undefined;
  const { data: fetchedScope } = useResourceScope(kind, name, !prefetched);
  const scopeData: ResourceScope | undefined = prefetched
    ? { scope: presetScope, supports_scope: true }
    : fetchedScope;
  const { data: agentsData } = useAgents();
  const update = useUpdateResourceScope(kind, name);
  const enable = useEnableResource();
  const disable = useDisableResource();

  const busy = update.isPending || enable.isPending || disable.isPending;
  // While the scope query is in flight, assume the kind supports scope (the
  // two kinds mounting this control today do); the fallback only matters once
  // the server has said otherwise.
  const supportsScope = scopeData ? scopeData.supports_scope : true;
  const scope = scopeData?.scope ?? null;
  const isSelected = enabled && scope !== null;

  // Shared look for one segment of the group: the active one is filled, the
  // rest are quiet, and every one of them is inert while a write is in flight.
  const segment = (active: boolean) =>
    ({
      type: "button",
      size: "sm",
      variant: active ? "secondary" : "ghost",
      "aria-pressed": active,
      disabled: busy,
    }) as const;

  const enableIfNeeded = () => {
    if (!enabled) enable.mutate({ kind, name });
  };
  const goDisabled = () => disable.mutate({ kind, name });
  const goEveryAgent = () => {
    enableIfNeeded();
    if (scope !== null) update.mutate(null);
  };
  const goSelected = () => {
    enableIfNeeded();
    if (scope === null) update.mutate([]);
  };

  if (!supportsScope) {
    return (
      <div className={GROUP_CLASS} data-testid="scope-control">
        <Button {...segment(!enabled)} onClick={goDisabled}>
          {t("common.disabled")}
        </Button>
        <Button {...segment(enabled)} onClick={enableIfNeeded}>
          {t("common.enabled")}
        </Button>
      </div>
    );
  }

  const selected = scope ?? [];
  const registered = (agentsData ?? []).map((a) => a.name);
  const unknown = selected.filter((n) => !registered.includes(n));
  const rows = [
    ...registered.map((n) => ({ name: n, known: true })),
    ...unknown.map((n) => ({ name: n, known: false })),
  ];

  const toggleAgent = (agentName: string, checked: boolean) => {
    update.mutate(checked ? [...selected, agentName] : selected.filter((a) => a !== agentName));
  };

  const selectedLabel =
    selected.length > 0
      ? `${t("scope.selectedAgents")} (${selected.length})`
      : t("scope.selectedAgents");

  return (
    <div className={GROUP_CLASS} data-testid="scope-control">
      <Button {...segment(!enabled)} onClick={goDisabled}>
        {t("common.disabled")}
      </Button>
      <Button {...segment(enabled && scope === null)} onClick={goEveryAgent}>
        {t("scope.everyAgent")}
      </Button>
      <Popover>
        <PopoverTrigger asChild>
          <Button {...segment(isSelected)} onClick={goSelected}>
            {selectedLabel}
            <ChevronDown className="size-3.5" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-80 space-y-3 p-3">
          <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>

          {selected.length === 0 ? (
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
                    checked={selected.includes(row.name)}
                    disabled={busy}
                    aria-label={row.name}
                    onChange={(e) => toggleAgent(row.name, e.target.checked)}
                  />
                  <span className="font-medium">{row.name}</span>
                  {!row.known ? <Badge variant="outline">{t("scope.unknownAgent")}</Badge> : null}
                </label>
              ))}
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
