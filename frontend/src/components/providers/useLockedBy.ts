// src/components/providers/useLockedBy.ts — who a live provider's protocol is locked for, in words.
//
// The daemon refuses to move the wire of an `is_active` provider (409
// PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE), so the Overview and the Edit dialog
// say so up front and name the agents running on it.
import { useTranslation } from "react-i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { Provider } from "@/lib/api/providers";
import type { ProviderUse } from "@/lib/providers/usedBy";

/** The agents the protocol is locked for, or "" when it is not locked. */
export function useLockedBy(provider: Provider, use: ProviderUse): string {
  const { t, i18n } = useTranslation();
  if (!provider.is_active) return "";
  const names = use.agents.map(({ agent }) => agentTypeLabel(agent.type));
  if (names.length === 0) return t("providers.endpoint.anAgent");
  return new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(names);
}
