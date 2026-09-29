// src/components/agents/overview/useProviderLabel.ts — the "Provider" line: which connection this agent type runs on.
//
// The active connection is the enabled one routed to this agent type that is
// marked active (the same test the Model tab's picker makes); with none, the
// agent runs on its own built-in login. `undefined` while the list loads.
import { useTranslation } from "react-i18next";

import type { AgentType } from "@/lib/api/agents";
import { useProviders } from "@/lib/hooks/useProviders";
import { displayName } from "@/lib/resourceTitle";

export function useProviderLabel(type: AgentType): string | undefined {
  const { t } = useTranslation();
  const providers = useProviders();
  if (!providers.data) return providers.isError ? t("common.emptyValue") : undefined;
  const active = providers.data.find(
    (p) => p.enabled && p.is_active && (p.compatible_agents ?? []).includes(type),
  );
  return active ? displayName(active) : t(`agents.overviewTab.model.builtin.${type}`);
}
