// src/components/agents/sessions/SessionList.tsx — the list side of the Sessions tab.
//
// Search (title or project, sent to the server — debounced, since a keystroke
// can cost a transcript parse on a cold reader), a project filter, a sort, the
// total, and the sessions page by page: the listing is cursor-paged, so each
// page is its own query (SessionListPage) and "Load more" appends the next one
// with the cursor the last page returned. A cursor is bound to the query it was
// issued for, so changing the search, project or sort starts again from page 1.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SessionListPage } from "@/components/agents/sessions/SessionListPage";
import { projectName } from "@/components/agents/sessions/sessionTime";
import { SearchInput } from "@/components/SearchInput";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TranscriptListParams, TranscriptSort } from "@/lib/api/agentTranscripts";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { TRANSCRIPTS_PAGE_SIZE, useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";

const ALL = "__all__";
const SORTS: TranscriptSort[] = ["last_activity_at", "started_at", "message_count"];

export function SessionList({
  uid,
  projects,
  selected,
  onOpen,
}: {
  uid: string;
  /** Project paths to offer in the filter. */
  projects: string[];
  selected: string | null;
  onOpen: (sourcePath: string) => void;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [project, setProject] = useState(ALL);
  const [sort, setSort] = useState<TranscriptSort>("last_activity_at");
  // One entry per loaded page: the cursor that reads it (page 1 needs none).
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const q = useDebouncedValue(search).trim();

  const params: TranscriptListParams = {
    q: q || undefined,
    project: project === ALL ? undefined : project,
    sort,
    order: "desc",
    limit: TRANSCRIPTS_PAGE_SIZE,
  };
  // The first page is also the source of the total (shared cache with page 1).
  const first = useAgentTranscripts(uid, params);
  const restart = () => setCursors([undefined]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <SearchInput
        value={search}
        onChange={(v) => {
          setSearch(v);
          restart();
        }}
        placeholder={t("agents.sessionsTab.searchPlaceholder")}
        ariaLabel={t("agents.sessionsTab.searchPlaceholder")}
      />
      <div className="flex items-center gap-2">
        <Select
          value={project}
          onValueChange={(v) => {
            setProject(v);
            restart();
          }}
        >
          <SelectTrigger className="min-w-0 flex-1" aria-label={t("agents.sessionsTab.project")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("agents.sessionsTab.allProjects")}</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p} value={p}>
                {projectName(p)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={sort}
          onValueChange={(v) => {
            setSort(v as TranscriptSort);
            restart();
          }}
        >
          <SelectTrigger className="w-36" aria-label={t("agents.sessionsTab.sort")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORTS.map((s) => (
              <SelectItem key={s} value={s}>
                {t(`agents.sessionsTab.sortBy.${s}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="shrink-0 text-xs tabular-nums text-text-muted">
          {first.data ? first.data.total : ""}
        </span>
      </div>
      <ul className="-mx-1 min-h-0 flex-1 overflow-auto" data-testid="session-list">
        {cursors.map((cursor, i) => (
          <SessionListPage
            key={cursor ?? "first"}
            uid={uid}
            params={{ ...params, cursor }}
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
