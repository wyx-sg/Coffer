// components/chat/ConversationList.tsx
// Collapsible history column listing all conversations, with title search.
// Search filters the already-loaded list client-side — fine for a local-first
// single-user vault; server-side search is the scale path if lists grow large.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/SearchInput";
import type { Conversation } from "@/lib/api/chat";
import { ConversationListItem } from "./ConversationListItem";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  /** Which list is shown: the active threads or the archived ones. */
  view: "active" | "archived";
  onToggleView: () => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onArchive: (id: string) => void;
  onRestore: (id: string) => void;
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  view,
  onToggleView,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  onArchive,
  onRestore,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const archivedView = view === "archived";

  const trimmed = query.trim().toLowerCase();
  const filtered = trimmed
    ? conversations.filter((c) => c.title.toLowerCase().includes(trimmed))
    : conversations;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* One toolbar: view tabs + new-chat, then search — a single bordered
          band instead of two stacked thin rows. */}
      <div className="space-y-2 border-b border-border px-2 py-2">
        <div className="flex items-center justify-between gap-2">
          <div
            className="inline-flex rounded-md bg-muted p-0.5"
            role="tablist"
            aria-label={t("chat.history.filterLabel")}
          >
            {(["active", "archived"] as const).map((v) => {
              const selected = view === v;
              return (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => {
                    if (!selected) onToggleView();
                  }}
                  className={cn(
                    "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                    selected
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {v === "active"
                    ? t("chat.history.filterActive")
                    : t("chat.history.filterArchived")}
                </button>
              );
            })}
          </div>
          {!archivedView && (
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              onClick={onCreate}
              aria-label={t("chat.history.new")}
            >
              <Plus className="size-4" />
            </Button>
          )}
        </div>

        {conversations.length > 0 && (
          <SearchInput
            value={query}
            onChange={setQuery}
            ariaLabel={t("chat.history.search")}
            placeholder={t("chat.history.search")}
            className="[&_input]:h-8 [&_input]:text-xs"
          />
        )}
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
            {archivedView ? t("chat.history.archivedEmpty") : t("chat.history.empty")}
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
            onArchive={archivedView ? undefined : () => onArchive(conv.id)}
            onRestore={archivedView ? () => onRestore(conv.id) : undefined}
          />
        ))}
      </div>
    </div>
  );
}
