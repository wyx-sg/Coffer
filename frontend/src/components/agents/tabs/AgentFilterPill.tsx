// src/components/agents/tabs/AgentFilterPill.tsx — the removable "Agent: <name> ×" pill a page shows while `?agent=` filters it.
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { AgentFilter } from "@/lib/agents/agentFilter";

export function AgentFilterPill({ filter }: { filter: AgentFilter | null }) {
  const { t } = useTranslation();
  if (!filter?.label) return null;
  return (
    <span className="inline-flex h-control-sm items-center gap-1 rounded-md border border-border bg-surface-selected pl-2.5 pr-1 text-xs text-text-muted">
      <span>
        {t("agents.filterPill.agent")}: <span className="font-label text-text">{filter.label}</span>
      </span>
      <button
        type="button"
        onClick={filter.clear}
        aria-label={t("agents.filterPill.remove", { name: filter.label })}
        className="inline-flex size-5 items-center justify-center rounded-sm text-text-subtle hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      >
        <X className="size-3" aria-hidden />
      </button>
    </span>
  );
}
