// src/components/agents/overview/useProviderLabel.ts — the "Provider" line: which connection this agent type runs on.
//
// The connection is the one the agent's record names, if it is still enabled
// and reaches the agent (the same test the Model tab makes); with none, the
// agent runs on its own built-in login. `undefined` while the list loads.
import { useTranslation } from "react-i18next";

import type { AgentOut } from "@/lib/api/agents";
import { useProviders } from "@/lib/hooks/useProviders";
import { activeProviderFor } from "@/lib/providers/usedBy";
import { displayName } from "@/lib/resourceTitle";

export function useProviderLabel(agent: AgentOut): string | undefined {
  const { t } = useTranslation();
  const providers = useProviders();
  if (!providers.data) return providers.isError ? t("common.emptyValue") : undefined;
  const active = activeProviderFor(agent, providers.data);
  return active ? displayName(active) : t(`agents.overviewTab.model.builtin.${agent.type}`);
}
