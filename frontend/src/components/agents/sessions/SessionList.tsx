// src/components/agents/sessions/SessionList.tsx — the list side of the Sessions tab.
//
// The agent's sessions, most recently active first, with their total above and
// the sessions page by page: the listing is cursor-paged, so each page is its
// own query (SessionListPage) and "Load more" appends the next one with the
// cursor the last page returned.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SessionListPage } from "@/components/agents/sessions/SessionListPage";
import type { TranscriptListParams } from "@/lib/api/agentTranscripts";
import { TRANSCRIPTS_PAGE_SIZE, useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";

const PARAMS: TranscriptListParams = {
  sort: "last_activity_at",
  order: "desc",
  limit: TRANSCRIPTS_PAGE_SIZE,
};

export function SessionList({
  uid,
  selected,
  onOpen,
}: {
  uid: string;
  selected: string | null;
  onOpen: (sourcePath: string) => void;
}) {
  const { t } = useTranslation();
  // One entry per loaded page: the cursor that reads it (page 1 needs none).
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  // The first page is also the source of the total (shared cache with page 1).
  const first = useAgentTranscripts(uid, PARAMS);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      {first.data ? (
        <p className="shrink-0 px-1 text-xs tabular-nums text-text-muted">
          {t("agents.sessionsTab.count", { count: first.data.total })}
        </p>
      ) : null}
      <ul className="-mx-1 min-h-0 flex-1 overflow-auto" data-testid="session-list">
        {cursors.map((cursor, i) => (
          <SessionListPage
            key={cursor ?? "first"}
            uid={uid}
            params={{ ...PARAMS, cursor }}
            isLast={i === cursors.length - 1}
            selected={selected}
            onOpen={onOpen}
            onMore={(next) => setCursors((cs) => [...cs, next])}
          />
        ))}
      </ul>
    </div>
  );
}
