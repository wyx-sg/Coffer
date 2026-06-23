// frontend/src/components/knowledge_base/KnowledgeBaseDocStatus.tsx
// Maps a KB document's embed_status (done | embedding | queued | running |
// error) to the shared StatusBadge. Kept apart so the doc tree/table stays
// within its size budget; mirrors AgentConversationsStatus.tsx.
import { useTranslation } from "react-i18next";

import { StatusBadge, type StatusTone } from "@/components/StatusBadge";

const MAP: Record<string, { tone: StatusTone; key: string; pulse?: boolean }> = {
  done: { tone: "success", key: "statusDone" },
  embedding: { tone: "info", key: "statusEmbedding", pulse: true },
  queued: { tone: "info", key: "statusQueued" },
  running: { tone: "info", key: "statusRunning", pulse: true },
  error: { tone: "danger", key: "statusError" },
};

export function DocEmbedStatus({ status }: { status?: string | null }) {
  const { t } = useTranslation();
  const m = status ? MAP[status] : undefined;
  if (!m) return null; // unknown / unwired → no badge
  return (
    <StatusBadge
      tone={m.tone}
      label={t(`knowledgeBases.detail.embedStatus.${m.key}`)}
      pulse={m.pulse}
    />
  );
}
