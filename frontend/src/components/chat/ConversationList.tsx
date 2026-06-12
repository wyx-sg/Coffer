// components/chat/ConversationList.tsx
// Collapsible history column listing all conversations.
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
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
        {conversations.map((conv) => (
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
