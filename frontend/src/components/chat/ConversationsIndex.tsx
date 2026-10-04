// src/components/chat/ConversationsIndex.tsx — `/conversations`: the page opens
// on the list, never on a welcome or suggestions page (spec chat "Show every
// conversation on the Conversations page"). A header with New conversation as
// the primary action, the filter row, then every conversation of every source
// grouped by day; with none at all, one quiet empty state.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquare, Plus } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { useTableSelection } from "@/components/DataTableSelection";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { translateApiError } from "@/lib/api/errors";
import type { Conversation } from "@/lib/api/chat";
import { channelPlatform } from "@/lib/channels/channelState";
import { clearFilters, isFiltered } from "@/lib/conversations/filters";
import { useChannels } from "@/lib/hooks/useChannels";
import type { ChatController } from "@/lib/hooks/useChatController";
import { useConversationBatch } from "@/lib/hooks/useConversationBatch";
import { useDeleteConversation } from "@/lib/hooks/useConversations";
import { channelHeading } from "@/components/channel/channelLabels";
import { ConversationsBulkBar } from "./ConversationsBulkBar";
import { ConversationsFilterBar, type SourceChannel } from "./ConversationsFilterBar";
import { ConversationsList } from "./ConversationsList";

interface Props {
  c: ChatController;
  onNew: () => void;
  agentNames: ReadonlyMap<string, string>;
}

const rowKey = (c: { id: string }) => c.id;

export function ConversationsIndex({ c, onNew, agentNames }: Props) {
  const { t } = useTranslation();
  const sel = useTableSelection(c.listConversations, rowKey);
  const batch = useConversationBatch();
  const deleteConv = useDeleteConversation();
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const { data: channelRows } = useChannels();
  const channels: SourceChannel[] = useMemo(
    () =>
      (channelRows ?? []).map((r) => ({
        uid: r.uid,
        heading: channelHeading(r),
        platform: channelPlatform(r.config),
      })),
    [channelRows],
  );

  // A different view (filters, archived) starts with nothing ticked.
  const { filters } = c;
  const { clear } = sel;
  useEffect(() => clear(), [filters, clear]);
  // Every filter is the server's, so a page holds only matching rows: the list
  // reads the next page only when the reader scrolls to its end.
  const { listLoading, hasMore, isLoadingMore, loadMore } = c;
  const drained = c.listConversations.length === 0;
  const narrowed = isFiltered(filters);
  const none = !listLoading && drained && !narrowed && !c.listError;
  const total = c.total ?? c.listConversations.length;

  const noMatches = !listLoading && drained && !hasMore && !c.listError && narrowed;

  // Select all means every conversation the view holds: the pages not read
  // yet are read first, then everything is ticked. Ticked again, it clears.
  const { listConversations, loadAll } = c;
  const { setMany } = sel;
  const [selectingAll, setSelectingAll] = useState(false);
  const shownIds = useMemo(() => listConversations.map(rowKey), [listConversations]);
  const tickedShown = sel.selectedRows.length;
  const allTicked = tickedShown > 0 && tickedShown === shownIds.length && !hasMore;
  const toggleAll = () => {
    if (allTicked || selectingAll) {
      setSelectingAll(false);
      clear();
      return;
    }
    setMany(shownIds, true);
    if (hasMore) {
      setSelectingAll(true);
      void loadAll();
    }
  };
  useEffect(() => {
    if (!selectingAll || hasMore || isLoadingMore) return;
    setMany(shownIds, true);
    setSelectingAll(false);
  }, [selectingAll, hasMore, isLoadingMore, shownIds, setMany]);
  useEffect(() => setSelectingAll(false), [filters]);

  const newButton = (
    <Button onClick={onNew}>
      <Plus aria-hidden /> {t("conversations.new.action")}
    </Button>
  );
  const header = (
    <PageHeader
      title={t("conversations.title")}
      subtitle={t("conversations.subtitle")}
      actions={newButton}
    />
  );

  if (none && !filters.archived) {
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

  const archive = (conv: Conversation) =>
    void batch.run(filters.archived ? "unarchive" : "archive", [conv.id]);

  return (
    <div className="space-y-5">
      {header}
      {sel.selectedRows.length > 0 ? (
        <ConversationsBulkBar
          selected={sel.selectedRows}
          total={Math.max(total, sel.selectedRows.length)}
          archivedView={filters.archived}
          onClear={sel.clear}
        />
      ) : (
        <ConversationsFilterBar
          filters={filters}
          onChange={c.setFilters}
          agents={c.agents}
          channels={channels}
          clearInList={noMatches}
        />
      )}
      {c.listError && drained ? (
        <EmptyState
          tone="error"
          title={t("conversations.list.loadFailed")}
          description={translateApiError(t, c.listError)}
          action={
            <Button variant="outline" size="sm" onClick={c.refetchList}>
              {t("common.retry")}
            </Button>
          }
        />
      ) : !listLoading && drained && !hasMore ? (
        <EmptyState
          icon={MessageSquare}
          title={
            filters.archived && !narrowed
              ? t("conversations.history.archivedEmpty")
              : t("conversations.list.noMatches")
          }
          action={
            narrowed ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => c.setFilters(clearFilters(filters))}
              >
                {t("conversations.list.clearFilters")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto">
            <ConversationsList
              conversations={c.listConversations}
              isLoading={listLoading}
              loadingMore={isLoadingMore}
              agentNames={agentNames}
              hrefFor={c.pathFor}
              archivedView={filters.archived}
              selection={{ selected: sel.keys, setMany: sel.setMany }}
              selectAll={{
                checked: allTicked,
                indeterminate: !allTicked && (tickedShown > 0 || selectingAll),
                onToggle: toggleAll,
              }}
              onArchive={archive}
              onDelete={setDeleting}
            />
          </div>
          <LoadMoreFooter
            loaded={c.listConversations.length}
            hasMore={hasMore}
            loading={isLoadingMore}
            onMore={loadMore}
            autoLoad
          />
        </>
      )}

      {/* Only Coffer's copy goes: the agent's own files and session stay. */}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t("conversations.delete.title", { title: deleting?.title ?? "" })}
        description={t("conversations.delete.body", { title: deleting?.title ?? "" })}
        confirmLabel={t("conversations.delete.confirm")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteConversation")}
        pending={deleteConv.isPending}
        onConfirm={() => {
          if (deleting) deleteConv.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
      />
    </div>
  );
}
