// frontend/src/components/agents/AgentConversationsStatus.tsx
// Maps a transcript's distill_status (done | stale | never | queued | running |
// error) to the shared StatusBadge. ``stale`` means the session was distilled
// before but its transcript has grown since — its newer content is NOT captured.
// Kept apart so AgentConversationsTab stays within its size budget.
import { useTranslation } from "react-i18next";

import { StatusBadge, type StatusTone } from "@/components/StatusBadge";

const MAP: Record<string, { tone: StatusTone; key: string; pulse?: boolean }> = {
  done: { tone: "success", key: "statusDone" },
  stale: { tone: "warning", key: "statusStale" },
  queued: { tone: "info", key: "statusQueued" },
  running: { tone: "info", key: "statusRunning", pulse: true },
  error: { tone: "danger", key: "statusError" },
};

export function DistillStatus({ status }: { status?: string | null }) {
  const { t } = useTranslation();
  const m = status ? MAP[status] : undefined;
  if (!m) {
    return (
      <StatusBadge tone="neutral" label={t("agents.conversationsTab.statusNever")} />
    );
  }
  return (
    <StatusBadge
      tone={m.tone}
      label={t(`agents.conversationsTab.${m.key}`)}
      pulse={m.pulse}
    />
  );
}
