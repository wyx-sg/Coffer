// src/components/providers/useUserNames.ts — "Codex and speech to text": who runs on a provider, in words.
import { useTranslation } from "react-i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { ProviderUse } from "@/lib/providers/usedBy";

/** The users of a provider as one phrase in the UI language, or "" for none. */
export function useUserNames(use: ProviderUse): string {
  const { t, i18n } = useTranslation();
  const names = [
    ...use.agents.map(({ agent }) => agentTypeLabel(agent.type)),
    ...(use.transcribe ? [t("providers.usedBy.transcribe")] : []),
  ];
  if (names.length === 0) return "";
  return new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(names);
}
