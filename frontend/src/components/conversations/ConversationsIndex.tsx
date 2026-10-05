// src/components/conversations/ConversationsIndex.tsx — `/conversations`: the
// conversations IM channels opened, as a list and nothing else (spec chat
// "Show channel conversations on the Conversations page"). A header with no
// primary action, the filter row, then the conversations grouped by day; with
// none at all, one quiet empty state. Rows are the shared SessionRow: pressing
// one opens its session in the preferred terminal (spec chat "Open a
// conversation in the terminal").
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquare } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { channelHeading } from "@/components/channel/channelLabels";
import { DeleteSessionDialog } from "@/components/sessions/DeleteSessionDialog";
import { SessionList } from "@/components/sessions/SessionList";
import { useOpenSession } from "@/components/sessions/useOpenSession";
import { Button } from "@/components/ui/button";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { translateApiError } from "@/lib/api/errors";
import { channelPlatform } from "@/lib/channels/channelState";
import { clearFilters, isFiltered } from "@/lib/conversations/filters";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useChannels } from "@/lib/hooks/useChannels";
import { useConversationFilters } from "@/lib/hooks/useConversationFilters";
import { useConversationList } from "@/lib/hooks/useConversationList";
import {
  useDeleteConversation,
  useInterruptConversation,
  useRenameConversation,
} from "@/lib/hooks/useConversations";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { conversationRow, type SessionRowData } from "@/lib/sessions/rows";
import { ConversationsFilterBar, type SourceChannel } from "./ConversationsFilterBar";

export function ConversationsIndex() {
  const { t } = useTranslation();
  const { filters, setFilters } = useConversationFilters();
  // Typing is the URL's, instantly; the request follows once it settles.
  const q = useDebouncedValue(filters.q.trim());
  const list = useConversationList({ q, source: filters.source, agent: filters.agent });
  const { data: agents = [] } = useAgentProviders();
  const { data: channelRows } = useChannels();
  const rename = useRenameConversation();
  const remove = useDeleteConversation();
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
  const rows = useMemo(() => list.items.map(conversationRow), [list.items]);

  const onRename = useCallback(
    (row: SessionRowData, title: string) => rename.mutateAsync({ id: row.id, title }),
    [rename],
  );
  const onStop = useCallback((row: SessionRowData) => stop.mutate(row.id), [stop]);

  const narrowed = isFiltered(filters);
  const drained = rows.length === 0;
  const none = !list.isLoading && drained && !narrowed && !list.error;
  const noMatches = !list.isLoading && drained && !list.hasMore && !list.error && narrowed;
  const header = (
    <PageHeader title={t("conversations.title")} subtitle={t("conversations.subtitle")} />
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
      {list.error && drained ? (
        <EmptyState
          tone="error"
          title={t("conversations.list.loadFailed")}
          description={translateApiError(t, list.error)}
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
          <div className="overflow-x-auto">
            <SessionList
              rows={rows}
              ariaLabel={t("conversations.list.ariaLabel")}
              isLoading={list.isLoading}
              loadingMore={list.isLoadingMore}
              grouped
              showChannel
              agentNames={agentNames}
              stoppingId={stop.isPending ? (stop.variables ?? null) : null}
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
        kind="conversation"
        pending={remove.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={(row) => remove.mutateAsync(row.id)}
      />
    </div>
  );
}
