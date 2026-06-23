// frontend/src/components/agents/AgentMemoryImportStatus.tsx
// Maps a native-memory store's import_status (queued | running | error) to the
// shared StatusBadge. Idle/finished stores carry no in-flight status, so they
// render a neutral "—" placeholder. Kept apart so AgentMemoryTab stays within
// its size budget (mirrors AgentConversationsStatus).
import { useTranslation } from "react-i18next";

import { StatusBadge, type StatusTone } from "@/components/StatusBadge";

const MAP: Record<string, { tone: StatusTone; key: string; pulse?: boolean }> = {
  queued: { tone: "info", key: "statusQueued" },
  running: { tone: "info", key: "statusRunning", pulse: true },
  error: { tone: "danger", key: "statusError" },
};

export function NativeImportStatus({ status }: { status?: string | null }) {
  const { t } = useTranslation();
  const m = status ? MAP[status] : undefined;
  if (!m) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return <StatusBadge tone={m.tone} label={t(`agents.memoryTab.${m.key}`)} pulse={m.pulse} />;
}
