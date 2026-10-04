// src/components/providers/useLockedBy.ts — who a live provider's protocol is locked for, in words.
//
// The daemon refuses to move the wire of a provider an agent runs on (409
// PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE), so the Overview and the Edit dialog
// say so up front and name the agents running on it.
import { useTranslation } from "react-i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { ProviderUse } from "@/lib/providers/usedBy";

/** The agents the protocol is locked for, or "" when it is not locked. */
export function useLockedBy(use: ProviderUse): string {
  const { i18n } = useTranslation();
  const names = use.agents.map(({ agent }) => agentTypeLabel(agent.type));
  if (names.length === 0) return "";
  return new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(names);
}
