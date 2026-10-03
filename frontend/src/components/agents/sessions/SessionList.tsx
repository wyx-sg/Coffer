// src/components/agents/sessions/SessionList.tsx — the list side of the Sessions tab (boards 2.1.52, 2.1.54).
//
// A search field and a Project pill over the agent's sessions, most recently
// active first. No count line, no sort control, no refresh button: the list
// reads again when the window gets focus. The listing is cursor-paged, so each
// page is its own query (SessionListPage) and "Load more" appends the next one
// with the cursor the last page returned. A new search or project starts the
// pages over.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ProjectPill } from "@/components/agents/sessions/ProjectPill";
import { SessionListPage } from "@/components/agents/sessions/SessionListPage";
import { SearchInput } from "@/components/SearchInput";
import type { TranscriptListParams } from "@/lib/api/agentTranscripts";
import { TRANSCRIPTS_PAGE_SIZE } from "@/lib/hooks/useAgentTranscripts";

const SORT: TranscriptListParams = { sort: "last_activity_at", order: "desc" };

/** The text, once it has stopped changing for a moment. */
function useSettled(value: string, ms = 250): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return settled;
}

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
  const [search, setSearch] = useState("");
  const [project, setProject] = useState<string | null>(null);
  const q = useSettled(search.trim());

  return (
    <>
      <div className="flex shrink-0 items-center gap-2 p-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder={t("agents.sessionsTab.search")}
          ariaLabel={t("agents.sessionsTab.search")}
          shortcut="/"
          className="min-w-0 flex-1"
        />
        <ProjectPill uid={uid} value={project} onChange={setProject} />
      </div>
      {/* New filters, new pages: keyed so the cursors start over. */}
      <Pages
        key={`${q}\u0000${project ?? ""}`}
        uid={uid}
        q={q}
        project={project}
        selected={selected}
        onOpen={onOpen}
      />
    </>
  );
}

function Pages({
  uid,
  q,
  project,
  selected,
  onOpen,
}: {
  uid: string;
  q: string;
  project: string | null;
  selected: string | null;
  onOpen: (sourcePath: string) => void;
}) {
  // One entry per loaded page: the cursor that reads it (page 1 needs none).
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const base: TranscriptListParams = {
    ...SORT,
    limit: TRANSCRIPTS_PAGE_SIZE,
    q: q || undefined,
    project: project ?? undefined,
  };
  return (
    <ul className="min-h-0 flex-1 overflow-auto px-1.5 pb-2" data-testid="session-list">
      {cursors.map((cursor, i) => (
        <SessionListPage
          key={cursor ?? "first"}
          uid={uid}
          params={{ ...base, cursor }}
          isLast={i === cursors.length - 1}
          selected={selected}
          onOpen={onOpen}
          onMore={(next) => setCursors((cs) => [...cs, next])}
        />
      ))}
    </ul>
  );
}
