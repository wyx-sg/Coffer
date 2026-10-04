// src/components/agents/sessions/SessionListPage.tsx — one page of the Sessions list.
// Each row is the session's title, its project and message count, and how long
// ago it was last active; the open session is marked. The last page loaded
// offers "Load more" while the server has a cursor for the next one.
import { useTranslation } from "react-i18next";

import { ageOf, projectName } from "@/components/agents/sessions/sessionTime";
import { Button } from "@/components/ui/button";
import type { TranscriptListParams } from "@/lib/api/agentTranscripts";
import { translateApiError } from "@/lib/api/errors";
import { shortDay } from "@/lib/skills/format";
import { useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";
import { cn } from "@/lib/utils";

function AgeLabel({ iso }: { iso: string | null }) {
  const { t, i18n } = useTranslation();
  if (!iso) return null;
  const age = ageOf(iso);
  const text =
    age.unit === "date"
      ? shortDay(iso, i18n.language)
      : age.unit === "now"
        ? t("agents.sessionsTab.age.now")
        : t(`agents.sessionsTab.age.${age.unit}`, { count: age.count });
  return <span className="shrink-0 pt-px text-xs tabular-nums text-text-muted">{text}</span>;
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
    return <li className="px-3 py-1.5 text-sm text-text-muted">{t("common.loading")}</li>;
  }
  if (page.error) {
    return (
      <li className="px-3 py-1.5 text-sm text-danger" role="alert">
        {translateApiError(t, page.error)}
      </li>
    );
  }
  const sessions = page.data?.sessions ?? [];
  const next = page.isPlaceholderData ? null : (page.data?.next_cursor ?? null);

  return (
    <>
      {sessions.length === 0 && !params.cursor ? (
        <li className="px-3 py-3 text-sm text-text-muted">{t("agents.sessionsTab.noMatch")}</li>
      ) : null}
      {sessions.map((s) => {
        const active = s.source_path === selected;
        return (
          <li key={s.source_path}>
            <button
              type="button"
              onClick={() => onOpen(s.source_path)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left transition-colors",
                active ? "bg-surface-selected" : "hover:bg-surface-hover",
              )}
            >
              <span className="min-w-0 flex-1">
                <span
                  className={cn(
                    "block truncate text-sm font-label",
                    s.title ? "text-text" : "text-text-muted",
                  )}
                >
                  {s.title ?? t("agents.sessionsTab.untitled")}
                </span>
                <span className="mt-0.5 block truncate text-xs text-text-muted">
                  {t("agents.sessionsTab.rowMeta", {
                    project: projectName(s.project_path) ?? t("common.emptyValue"),
                    count: s.message_count,
                  })}
                </span>
              </span>
              <AgeLabel iso={s.last_activity_at ?? s.started_at} />
            </button>
          </li>
        );
      })}
      {isLast && next ? (
        <li className="px-1.5 py-2">
          <Button variant="ghost" size="sm" className="w-full" onClick={() => onMore(next)}>
            {t("agents.sessionsTab.loadMore")}
          </Button>
        </li>
      ) : null}
    </>
  );
}
