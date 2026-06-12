// components/chat/ConversationList.tsx
// Collapsible history column listing all conversations, with title search.
// Search filters the already-loaded list client-side — fine for a local-first
// single-user vault; server-side search is the scale path if lists grow large.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/SearchInput";
import type { Conversation } from "@/lib/api/chat";
import { ConversationListItem } from "./ConversationListItem";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const trimmed = query.trim().toLowerCase();
  const filtered = trimmed
    ? conversations.filter((c) => c.title.toLowerCase().includes(trimmed))
    : conversations;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("chat.history.title")}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="size-7 p-0"
          onClick={onCreate}
          aria-label={t("chat.history.new")}
        >
          <Plus className="size-4" />
        </Button>
      </div>

      {conversations.length > 0 && (
        <div className="border-b border-border px-2 py-2">
          <SearchInput
            value={query}
            onChange={setQuery}
            ariaLabel={t("chat.history.search")}
            placeholder={t("chat.history.search")}
            className="[&_input]:h-8 [&_input]:text-xs"
          />
        </div>
      )}

      <div
        className="flex-1 overflow-y-auto px-2 py-2"
        role="listbox"
        aria-label={t("chat.history.ariaLabel")}
      >
        {loading && (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            {t("common.loading")}
          </p>
        )}
        {!loading && conversations.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            {t("chat.history.empty")}
          </p>
        )}
        {!loading && conversations.length > 0 && filtered.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            {t("chat.history.noMatches")}
          </p>
        )}
        {filtered.map((conv) => (
          <ConversationListItem
            key={conv.id}
            conversation={conv}
            isActive={conv.id === activeId}
            onSelect={() => onSelect(conv.id)}
            onRename={(title) => onRename(conv.id, title)}
            onDelete={() => onDelete(conv.id)}
          />
        ))}
      </div>
    </div>
  );
}
