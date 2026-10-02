// src/components/chat/ConversationsIndex.tsx — `/conversations`: the page opens
// on the list, never on a welcome or suggestions page (spec chat "Show every
// conversation on the Conversations page"). A header with the count and New
// conversation as a small secondary action, the filters, then every
// conversation of every source; with none at all, one quiet empty state.
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquare, Plus } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { useTableSelection } from "@/components/DataTableSelection";
import { Button } from "@/components/ui/button";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { clearFilters, isFiltered, type SourceFilter } from "@/lib/conversations/filters";
import type { ChatController } from "@/lib/hooks/useChatController";
import { ConversationsBulkBar } from "./ConversationsBulkBar";
import { ConversationsFilterBar } from "./ConversationsFilterBar";
import { ConversationsTable } from "./ConversationsTable";

interface Props {
  c: ChatController;
  onNew: () => void;
  agentNames: ReadonlyMap<string, string>;
  /** The narrowed-to channel's label, when the list is filtered to one channel. */
  channelLabel: string | null;
  /** The narrowed-to channel's platform, which the source switch shows. */
  channelSource?: SourceFilter | null;
}

const rowKey = (c: { id: string }) => c.id;

export function ConversationsIndex({
  c,
  onNew,
  agentNames,
  channelLabel,
  channelSource = null,
}: Props) {
  const { t } = useTranslation();
  const sel = useTableSelection(c.listConversations, rowKey);
  // A different view (filters, archived) starts with nothing ticked.
  const { source, channel, agent, archived } = c.filters;
  const { clear } = sel;
  useEffect(() => clear(), [source, channel, agent, archived, clear]);
  const none = !c.listLoading && c.allConversations.length === 0 && !c.searching;
  // A filter narrows what is loaded: a view it empties, with more to read,
  // keeps reading rather than saying there is nothing.
  const { listLoading, hasMore, isLoadingMore, loadMore } = c;
  const drained = c.listConversations.length === 0;
  useEffect(() => {
    if (!listLoading && drained && hasMore && !isLoadingMore) loadMore();
  }, [listLoading, drained, hasMore, isLoadingMore, loadMore]);
  const narrowed = isFiltered(c.filters) || c.searching;
  const clearAll = () => {
    c.setFilters(clearFilters(c.filters));
    c.setTitleSearch("");
  };
  const newButton = (
    <Button variant="outline" size="sm" onClick={onNew}>
      <Plus aria-hidden /> {t("conversations.new.action")}
    </Button>
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("conversations.title")}
        badges={
          c.listLoading || none ? null : (
            <span className="text-sm font-normal text-text-muted">
              {c.listConversations.length}
              {c.hasMore ? "+" : ""}
            </span>
          )
        }
        actions={newButton}
      />
      {none && !c.filters.archived && !isFiltered(c.filters) && c.titleSearch === "" ? (
        <EmptyState
          icon={MessageSquare}
          title={t("conversations.list.emptyTitle")}
          description={t("conversations.list.emptyBody")}
          action={newButton}
        />
      ) : (
        <>
          {sel.selectedRows.length > 0 ? (
            <ConversationsBulkBar
              selected={sel.selectedRows}
              archivedView={c.filters.archived}
              onClear={sel.clear}
            />
          ) : (
            <ConversationsFilterBar
              filters={c.filters}
              onChange={c.setFilters}
              agents={c.agents}
              channelLabel={channelLabel}
              channelSource={channelSource}
              search={c.titleSearch}
              onSearch={c.setTitleSearch}
            />
          )}
          {!c.listLoading && drained && !hasMore ? (
            <EmptyState
              icon={MessageSquare}
              title={
                c.filters.archived && !narrowed
                  ? t("conversations.history.archivedEmpty")
                  : t("conversations.list.noMatches")
              }
              action={
                narrowed ? (
                  <Button variant="outline" size="sm" onClick={clearAll}>
                    {t("conversations.list.clearFilters")}
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <ConversationsTable
                  conversations={c.listConversations}
                  isLoading={c.listLoading}
                  loadingMore={isLoadingMore || (drained && hasMore)}
                  agentNames={agentNames}
                  hrefFor={c.pathFor}
                  selection={{ selected: sel.keys, setMany: sel.setMany }}
                  notice={c.filters.archived ? t("conversations.history.archivedHelp") : undefined}
                />
              </div>
              <LoadMoreFooter
                loaded={c.allConversations.length}
                hasMore={hasMore}
                loading={isLoadingMore}
                onMore={loadMore}
                autoLoad
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
