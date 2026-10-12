// frontend/src/components/memory/useMemoryFacts.ts — one memory's facts in a line, for the drawer and the reader.
import { useTranslation } from "react-i18next";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { agentTypeLabel } from "@/lib/agents/display";
import type { HubEntry } from "@/lib/api/memoryTypes";

/** "feedback · Claude Code · this machine · updated 30m ago". */
export function useMemoryFacts(entry: HubEntry | null, machine: string): string {
  const { t, i18n } = useTranslation();
  if (!entry) return "";
  const from =
    entry.origin_machine === machine ? t("memory.entries.thisMachine") : entry.origin_machine;
  return [
    entry.type,
    `${agentTypeLabel(entry.origin_agent)} · ${from}`,
    entry.updated_at
      ? t("memory.drawer.updated", { when: formatRelativeTime(entry.updated_at, i18n.language) })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
