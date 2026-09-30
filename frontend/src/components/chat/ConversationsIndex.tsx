// src/components/chat/ConversationsIndex.tsx — `/conversations`: the page opens
// on the list, never on a welcome or suggestions page (spec chat "Show every
// conversation on the Conversations page"). A header with the count and New
// conversation as a small secondary action, the filters, then every
// conversation of every source; with none at all, one quiet empty state.
import { useTranslation } from "react-i18next";
import { MessageSquare, Plus } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { isFiltered } from "@/lib/conversations/filters";
import type { ChatController } from "@/lib/hooks/useChatController";
import { ConversationsFilterBar } from "./ConversationsFilterBar";
import { ConversationsTable } from "./ConversationsTable";

interface Props {
  c: ChatController;
  onNew: () => void;
  agentNames: ReadonlyMap<string, string>;
  /** The narrowed-to channel's label, when the list is filtered to one channel. */
  channelLabel: string | null;
}

export function ConversationsIndex({ c, onNew, agentNames, channelLabel }: Props) {
  const { t } = useTranslation();
  const none = !c.listLoading && c.allConversations.length === 0;
  const newButton = (
    <Button variant="outline" size="sm" onClick={onNew}>
      <Plus aria-hidden /> {t("conversations.new.action")}
    </Button>
  );

  return (
    <div className="space-y-5">
      <PageHeader
        icon={MessageSquare}
        title={t("conversations.title")}
        badges={
          c.listLoading ? null : (
            <span className="text-sm font-normal text-text-muted">
              {c.listConversations.length}
            </span>
          )
        }
        actions={newButton}
      />
      {none && !c.filters.archived && !isFiltered(c.filters) ? (
        <EmptyState
          icon={MessageSquare}
          title={t("conversations.list.emptyTitle")}
          description={t("conversations.list.emptyBody")}
          action={newButton}
        />
      ) : (
        <>
          <ConversationsFilterBar
            filters={c.filters}
            onChange={c.setFilters}
            agents={c.agents}
            channelLabel={channelLabel}
          />
          {!c.listLoading && c.listConversations.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title={
                c.filters.archived
                  ? t("conversations.history.archivedEmpty")
                  : t("conversations.list.noMatches")
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <ConversationsTable
                conversations={c.listConversations}
                isLoading={c.listLoading}
                agentNames={agentNames}
                hrefFor={c.pathFor}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
