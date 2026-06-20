// components/chat/ConversationListItem.tsx
// Single entry in the history column with inline rename and delete actions.
import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2, Check, X, Archive, ArchiveRestore } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { Conversation } from "@/lib/api/chat";

interface Props {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
  /** Archive action (active view). When absent, the archive button is hidden. */
  onArchive?: () => void;
  /** Restore action (archived view). When present, replaces archive + rename. */
  onRestore?: () => void;
}

export function ConversationListItem({
  conversation,
  isActive,
  onSelect,
  onRename,
  onDelete,
  onArchive,
  onRestore,
}: Props) {
  const { t } = useTranslation();
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) inputRef.current?.focus();
  }, [renaming]);

  const commitRename = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== conversation.title) onRename(trimmed);
    setRenaming(false);
  };

  const cancelRename = () => {
    setDraft(conversation.title);
    setRenaming(false);
  };

  if (renaming) {
    return (
      <div className="flex items-center gap-1 rounded-md bg-primary/5 px-2 py-1.5">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") cancelRename();
          }}
          className="flex-1 bg-transparent text-sm outline-none"
          aria-label={t("chat.history.renameAria")}
        />
        <Button variant="ghost" size="sm" className="size-6 p-0" onClick={commitRename}>
          <Check className="size-3.5" />
        </Button>
        <Button variant="ghost" size="sm" className="size-6 p-0" onClick={cancelRename}>
          <X className="size-3.5" />
        </Button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group flex cursor-pointer items-center gap-1 rounded-md px-2 py-1.5 text-sm transition-colors",
        isActive
          ? "bg-primary/10 text-primary"
          : "text-foreground/80 hover:bg-secondary hover:text-foreground",
      )}
      role="option"
      aria-selected={isActive}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      tabIndex={0}
    >
      <span className="flex-1 truncate">{conversation.title}</span>
      {conversation.channel_binding != null && (
        <span className="shrink-0 rounded-full border border-transparent bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-secondary-foreground">
          {t("chat.history.viaChannel", { channel: conversation.channel_binding.channel })}
        </span>
      )}
      {onRestore ? (
        <Button
          variant="ghost"
          size="sm"
          className="size-5 shrink-0 p-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onRestore();
          }}
          aria-label={t("chat.history.restore")}
        >
          <ArchiveRestore className="size-3" />
        </Button>
      ) : (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="size-5 shrink-0 p-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100"
            onClick={(e) => {
              e.stopPropagation();
              setDraft(conversation.title);
              setRenaming(true);
            }}
            aria-label={t("chat.history.rename")}
          >
            <Pencil className="size-3" />
          </Button>
          {onArchive && (
            <Button
              variant="ghost"
              size="sm"
              className="size-5 shrink-0 p-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onArchive();
              }}
              aria-label={t("chat.history.archive")}
            >
              <Archive className="size-3" />
            </Button>
          )}
        </>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="size-5 shrink-0 p-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100 hover:text-destructive"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        aria-label={t("chat.history.delete")}
      >
        <Trash2 className="size-3" />
      </Button>
    </div>
  );
}
