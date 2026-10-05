// src/components/conversations/ConversationsIndex.tsx — `/conversations`: every
// session of every managed agent, as a list and nothing else (spec chat "Show
// every agent's sessions on the Conversations page"). A header with New
// conversation, the filter row, one quiet line naming any agent whose sessions
// could not be read, then the sessions grouped by day; with none at all, one
// empty state. Rows are the shared SessionRow: pressing one opens its session in
// the preferred terminal (spec chat "Open a conversation in the terminal").
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquare } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { channelHeading } from "@/components/channel/channelLabels";
import { DeleteSessionDialog } from "@/components/sessions/DeleteSessionDialog";
import { SessionList } from "@/components/sessions/SessionList";
import { useOpenSession } from "@/components/sessions/useOpenSession";
import { NewConversationButton } from "@/components/conversations/NewConversationButton";
import { Button } from "@/components/ui/button";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { translateApiError } from "@/lib/api/errors";
import { channelPlatform } from "@/lib/channels/channelState";
import { clearFilters, isFiltered } from "@/lib/conversations/filters";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useChannels } from "@/lib/hooks/useChannels";
import { useConversationFilters } from "@/lib/hooks/useConversationFilters";
import { useAllAgentSessions, useSessionRowActions } from "@/lib/hooks/useAllAgentSessions";
import { useInterruptConversation } from "@/lib/hooks/useConversations";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { sessionRow, type SessionRowData } from "@/lib/sessions/rows";
import { ConversationsFilterBar, type SourceChannel } from "./ConversationsFilterBar";

export function ConversationsIndex() {
  const { t } = useTranslation();
  const { filters, setFilters } = useConversationFilters();
  // Typing is the URL's, instantly; the request follows once it settles.
  const q = useDebouncedValue(filters.q.trim());
  const list = useAllAgentSessions({ q, source: filters.source, agent: filters.agent });
  const { data: agents = [] } = useAgentProviders();
  const { data: channelRows } = useChannels();
  const { rename, remove } = useSessionRowActions();
  const stop = useInterruptConversation();
  const [deleting, setDeleting] = useState<SessionRowData | null>(null);
  const opener = useOpenSession();

  const agentNames = useMemo(
    () => new Map(agents.map((a) => [a.agent_key, a.display_name])),
    [agents],
  );
  const channels: SourceChannel[] = useMemo(
    () =>
      (channelRows ?? []).map((r) => ({
        uid: r.uid,
        heading: channelHeading(r),
        platform: channelPlatform(r.config),
      })),
    [channelRows],
  );
  const rows = useMemo(() => list.items.map(sessionRow), [list.items]);
  // The agents whose sessions could not be read, once each, named as the registry does.
  const unavailable = useMemo(
    () => [...new Set(list.extras.flat().map((u) => u.agent))].map((k) => agentNames.get(k) ?? k),
    [list.extras, agentNames],
  );

  const onRename = useCallback(
    (row: SessionRowData, title: string) => rename.mutateAsync({ row, title }),
    [rename],
  );
  const onStop = useCallback(
    (row: SessionRowData) => {
      if (row.conversationId) stop.mutate(row.conversationId);
    },
    [stop],
  );

  const narrowed = isFiltered(filters);
  const drained = rows.length === 0;
  // Nothing listed while an agent could not be read is not an empty list.
  const unread = drained && unavailable.length > 0;
  const failed = drained && (list.error != null || unread);
  const none = !list.isLoading && drained && !narrowed && !failed;
  const noMatches = !list.isLoading && drained && !list.hasMore && !failed && narrowed;
  const header = (
    <PageHeader
      title={t("conversations.title")}
      subtitle={t("conversations.subtitle")}
      actions={<NewConversationButton />}
    />
  );

  if (none) {
    return (
      <div className="space-y-5">
        {header}
        <EmptyState
          icon={MessageSquare}
          title={t("conversations.list.emptyTitle")}
          description={t("conversations.list.emptyBody")}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {header}
      <ConversationsFilterBar
        filters={filters}
        onChange={setFilters}
        agents={agents}
        channels={channels}
        clearInList={noMatches}
      />
      {failed ? (
        <EmptyState
          tone="error"
          title={t("conversations.list.loadFailed")}
          description={
            list.error
              ? translateApiError(t, list.error)
              : t("conversations.list.unavailable", {
                  count: unavailable.length,
                  agents: unavailable.join(", "),
                })
          }
          action={
            <Button variant="outline" size="sm" onClick={list.refetch}>
              {t("common.retry")}
            </Button>
          }
        />
      ) : noMatches ? (
        <EmptyState
          icon={MessageSquare}
          title={t("conversations.list.noMatches")}
          action={
            <Button variant="outline" size="sm" onClick={() => setFilters(clearFilters())}>
              {t("conversations.list.clearFilters")}
            </Button>
          }
        />
      ) : (
        <>
          {unavailable.length > 0 ? (
            <p className="flex items-center gap-1.5 text-xs text-text-muted" role="status">
              {t("conversations.list.unavailable", {
                count: unavailable.length,
                agents: unavailable.join(", "),
              })}
              <span aria-hidden>·</span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={list.refetch}
              >
                {t("common.retry")}
              </Button>
            </p>
          ) : null}
          <div className="overflow-x-auto">
            <SessionList
              rows={rows}
              ariaLabel={t("conversations.list.ariaLabel")}
              isLoading={list.isLoading}
              loadingMore={list.isLoadingMore}
              grouped
              showChannel
              agentNames={agentNames}
              stoppingId={
                stop.isPending
                  ? (rows.find((r) => r.conversationId === stop.variables)?.id ?? null)
                  : null
              }
              onPrimaryAction={opener.open}
              terminalLabel={opener.terminalLabel}
              otherTerminals={opener.otherTerminals}
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
        kind={deleting?.channel ? "conversation" : "session"}
        pending={remove.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={(row) => remove.mutateAsync(row)}
      />
    </div>
  );
}
