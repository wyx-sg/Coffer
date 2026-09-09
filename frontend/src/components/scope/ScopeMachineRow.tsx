// frontend/src/components/scope/ScopeMachineRow.tsx
//
// One machine's row in ScopeCard (ADR-045): the on/off switch and, for
// dual-axis kinds, its per-agent selector. Extracted from ScopeCard.tsx to
// keep that file under the component size limit; the row's own data shape
// (ScopeMachineRowData) and the "everywhere" wildcard sentinel are colocated
// here since they exist for this row's sake.
import { Laptop } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import type { Scope } from "@/lib/hooks/useScope";

export const WILDCARD = "*";

export interface ScopeMachineRowData {
  id: string;
  displayName: string;
  isLocal: boolean;
  isKnown: boolean;
}

export function ScopeMachineRow({
  row,
  value,
  dualAxis,
  agents,
  disabled,
  onToggle,
  onAllAgentsChange,
  onAgentToggle,
}: {
  row: ScopeMachineRowData;
  value: Scope[string] | undefined;
  dualAxis: boolean;
  agents: string[];
  disabled: boolean;
  onToggle: (on: boolean) => void;
  onAllAgentsChange: (all: boolean) => void;
  onAgentToggle: (agentName: string, checked: boolean) => void;
}) {
  const { t } = useTranslation();
  const on = value !== undefined;
  const allAgents = value === WILDCARD;
  const selectedAgents = Array.isArray(value) ? value : [];

  return (
    <div data-testid={`scope-row-${row.id}`} className="rounded-md border border-border/60 p-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {row.isLocal ? <Laptop className="size-3.5 text-muted-foreground" aria-hidden /> : null}
          <span className="text-sm font-medium">{row.displayName}</span>
          {row.isLocal ? <Badge variant="outline">{t("machines.thisMachine")}</Badge> : null}
          {!row.isKnown ? (
            <span className="text-xs text-muted-foreground">{t("scope.unknownMachine")}</span>
          ) : null}
        </div>
        <Switch
          checked={on}
          disabled={disabled}
          onCheckedChange={onToggle}
          aria-label={t("scope.rowToggle", { machine: row.displayName })}
        />
      </div>

      {dualAxis && on ? (
        <div className="mt-2 space-y-2 pl-1">
          <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            <Checkbox
              checked={allAgents}
              disabled={disabled}
              aria-label={t("scope.allAgents")}
              onChange={(e) => onAllAgentsChange(e.target.checked)}
            />
            {t("scope.allAgents")}
          </label>
          {!allAgents ? (
            <div className="flex flex-wrap gap-3 pl-1">
              {agents.length === 0 ? (
                <span className="text-xs text-muted-foreground">{t("scope.noAgents")}</span>
              ) : (
                agents.map((agentName) => (
                  <label
                    key={agentName}
                    className="flex w-fit cursor-pointer items-center gap-1.5 text-xs"
                  >
                    <Checkbox
                      checked={selectedAgents.includes(agentName)}
                      disabled={disabled}
                      aria-label={agentName}
                      onChange={(e) => onAgentToggle(agentName, e.target.checked)}
                    />
                    {agentName}
                  </label>
                ))
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
