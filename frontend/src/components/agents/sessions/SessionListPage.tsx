// src/components/agents/sessions/SessionListPage.tsx — one page of the Sessions list.
// Each row is the session's title, its project and message count, and how long
// ago it was last active; the open session is marked. The last page loaded
// offers "Load more" while the server has a cursor for the next one.
import { useTranslation } from "react-i18next";

import { ageOf, projectName } from "@/components/agents/sessions/sessionTime";
import { Button } from "@/components/ui/button";
import type { TranscriptListParams } from "@/lib/api/agentTranscripts";
import { translateApiError } from "@/lib/api/errors";
import { useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";
import { cn } from "@/lib/utils";

function AgeLabel({ iso }: { iso: string | null }) {
  const { t } = useTranslation();
  if (!iso) return null;
  const age = ageOf(iso);
  const text =
    age.unit === "date"
      ? age.date
      : age.unit === "now"
        ? t("agents.sessionsTab.age.now")
        : t(`agents.sessionsTab.age.${age.unit}`, { count: age.count });
  return <span className="shrink-0 text-2xs tabular-nums text-text-subtle">{text}</span>;
}

export function SessionListPage({
  uid,
  params,
  isLast,
  selected,
  onOpen,
  onMore,
}: {
  uid: string;
  params: TranscriptListParams;
  isLast: boolean;
  selected: string | null;
  onOpen: (sourcePath: string) => void;
  onMore: (cursor: string) => void;
}) {
  const { t } = useTranslation();
  const page = useAgentTranscripts(uid, params);

  if (page.isPending) {
    return <li className="px-2 py-1.5 text-sm text-text-muted">{t("common.loading")}</li>;
  }
  if (page.error) {
    return (
      <li className="px-2 py-1.5 text-sm text-danger" role="alert">
        {translateApiError(t, page.error)}
      </li>
    );
  }
  const sessions = page.data?.sessions ?? [];
  const next = page.isPlaceholderData ? null : (page.data?.next_cursor ?? null);

  return (
    <>
      {sessions.length === 0 && !params.cursor ? (
        <li className="px-2 py-3 text-sm text-text-muted">{t("agents.sessionsTab.noMatch")}</li>
      ) : null}
      {sessions.map((s) => (
        <li key={s.source_path}>
          <button
            type="button"
            onClick={() => onOpen(s.source_path)}
            aria-current={s.source_path === selected ? "true" : undefined}
            className={cn(
              "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
              s.source_path === selected
                ? "bg-surface-selected text-text"
                : "hover:bg-surface-hover hover:text-text",
            )}
          >
            <span className="min-w-0 flex-1">
              <span className="block break-words text-sm text-text">
                {s.title ?? t("agents.sessionsTab.untitled")}
              </span>
              <span className="block text-2xs text-text-muted">
                {t("agents.sessionsTab.rowMeta", {
                  project: projectName(s.project_path) ?? t("common.emptyValue"),
                  count: s.message_count,
                })}
              </span>
            </span>
            <AgeLabel iso={s.last_activity_at ?? s.started_at} />
          </button>
        </li>
      ))}
      {isLast && next ? (
        <li className="px-2 py-2">
          <Button variant="outline" size="sm" className="w-full" onClick={() => onMore(next)}>
            {t("agents.sessionsTab.loadMore")}
          </Button>
        </li>
      ) : null}
    </>
  );
}
