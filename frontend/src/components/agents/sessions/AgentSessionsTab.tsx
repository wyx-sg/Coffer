// src/components/agents/sessions/AgentSessionsTab.tsx — spec agent-registry
// "Open an agent's sessions from its Sessions tab".
// The agent detail page's Sessions tab: the agent's own sessions, asked of the
// agent itself, as the same rows the Conversations page uses — title, working
// directory and last activity, plus the channel, Running / Needs you and an
// inline Stop when the session is a channel conversation's. A search box over
// title and working directory filters in the server; the list pages by cursor
// as it is scrolled and reads again when the window gets focus. Pressing a row, or
// the main part of its split button, opens the session in the preferred terminal
// (asking first when it is busy); ⋯ holds Rename and Delete…. Coffer shows no
// session text.
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { DeleteSessionDialog } from "@/components/sessions/DeleteSessionDialog";
import { SessionList } from "@/components/sessions/SessionList";
import { useOpenSession } from "@/components/sessions/useOpenSession";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SearchInput } from "@/components/SearchInput";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import {
  useAgentSessions,
  useDeleteAgentSession,
  useRenameAgentSession,
} from "@/lib/hooks/useAgentSessions";
import { useInterruptConversation } from "@/lib/hooks/useConversations";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { sessionRow, type SessionRowData } from "@/lib/sessions/rows";

export function AgentSessionsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim());
  const list = useAgentSessions(agent.uid, q);
  const rename = useRenameAgentSession(agent.uid);
  const remove = useDeleteAgentSession(agent.uid);
  const stop = useInterruptConversation();
  const [deleting, setDeleting] = useState<SessionRowData | null>(null);
  const opener = useOpenSession(agent.type);
  const rows = useMemo(() => list.items.map(sessionRow), [list.items]);

  const onRename = useCallback(
    (row: SessionRowData, title: string) => rename.mutateAsync({ sessionId: row.id, title }),
    [rename],
  );
  const onStop = useCallback(
    (row: SessionRowData) => {
      if (row.conversationId) stop.mutate(row.conversationId);
    },
    [stop],
  );

  const searching = q !== "";
  const drained = rows.length === 0;
  if (list.error && drained) {
    return (
      <LoadErrorRow
        title={t("agents.sessionsTab.listFailed")}
        error={list.error}
        onRetry={list.refetch}
      />
    );
  }
  if (!list.isLoading && drained && !searching) {
    const dir = `${abbreviateHomePath(agent.config_dir)}/${agent.type === "codex" ? "sessions" : "projects"}`;
    return (
      <div className="rounded-xl border border-border px-6 py-8 text-center">
        <p className="text-sm font-semibold text-text">{t("agents.sessionsTab.emptyTitle")}</p>
        <p className="mt-1.5 text-xs text-text-muted">
          {t("agents.sessionsTab.emptyBody", {
            agent: agentTypeLabel(agent.type),
            dir,
            program: agentProgramName(agent.type),
          })}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder={t("agents.sessionsTab.search")}
        ariaLabel={t("agents.sessionsTab.search")}
        shortcut="/"
        className="w-72"
      />
      {!list.isLoading && drained ? (
        <p className="rounded-xl border border-border px-6 py-8 text-center text-sm text-text-muted">
          {t("agents.sessionsTab.noMatch")}
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <SessionList
              rows={rows}
              ariaLabel={t("agents.sessionsTab.ariaLabel")}
              isLoading={list.isLoading}
              loadingMore={list.isLoadingMore}
              stoppingId={
                stop.isPending ? rows.find((r) => r.conversationId === stop.variables)?.id : null
              }
              onPrimaryAction={opener.open}
              onCopyCommand={opener.copyCommand}
              canOpen={opener.canOpen}
              onRename={onRename}
              onDelete={setDeleting}
              onStop={onStop}
            />
          </div>
          <LoadMoreFooter
            loaded={rows.length}
            hasMore={list.hasMore}
            loading={list.isLoadingMore}
            onMore={list.loadMore}
            autoLoad
          />
        </>
      )}
      {opener.dialog}
      <DeleteSessionDialog
        row={deleting}
        kind="session"
        pending={remove.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={(row) => remove.mutateAsync(row.id)}
      />
    </div>
  );
}
