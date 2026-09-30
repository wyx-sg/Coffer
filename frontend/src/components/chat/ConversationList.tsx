// components/chat/ConversationList.tsx
// The list beside an open conversation: the same conversations, in the same
// order and under the same URL filters as the full list, compact enough to sit
// in a split pane, with a title search over what is loaded (a local-first,
// single-user list; server-side search is the scale path) and New conversation.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/SearchInput";
import type { Conversation } from "@/lib/api/chat";
import { ConversationListItem } from "./ConversationListItem";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  /** The full list, with the filters this pane shows. */
  listPath: string;
  hrefFor: (id: string) => string;
  agentNames: ReadonlyMap<string, string>;
  onCreate: () => void;
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  listPath,
  hrefFor,
  agentNames,
  onCreate,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const trimmed = query.trim().toLowerCase();
  const filtered = trimmed
    ? conversations.filter((c) => c.title.toLowerCase().includes(trimmed))
    : conversations;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="space-y-2 border-b border-border-subtle px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <Link
            to={listPath}
            className="inline-flex items-center gap-1 text-xs text-text-subtle transition-colors duration-fast hover:text-text"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            {t("conversations.title")}
          </Link>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onCreate}
            aria-label={t("conversations.new.action")}
          >
            <Plus aria-hidden />
          </Button>
        </div>
        {conversations.length > 0 && (
          <SearchInput
            value={query}
            onChange={setQuery}
            ariaLabel={t("conversations.history.search")}
            placeholder={t("conversations.history.search")}
            className="[&_input]:h-8 [&_input]:text-xs"
          />
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {loading && (
          <p className="px-2 py-4 text-center text-xs text-text-muted">{t("common.loading")}</p>
        )}
        {!loading && conversations.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-text-muted">
            {t("conversations.list.emptyTitle")}
          </p>
        )}
        {!loading && conversations.length > 0 && filtered.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-text-muted">
            {t("conversations.history.noMatches")}
          </p>
        )}
        {filtered.length > 0 && (
          <ul className="space-y-0.5" aria-label={t("conversations.history.ariaLabel")}>
            {filtered.map((conv) => (
              <ConversationListItem
                key={conv.id}
                conversation={conv}
                isActive={conv.id === activeId}
                href={hrefFor(conv.id)}
                agentName={agentNames.get(conv.agent_key)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
