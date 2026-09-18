// components/chat/ConversationListItem.tsx
// Single entry in the history column: the title is the button that opens the
// thread; rename / archive / restore / delete sit beside it as their own
// buttons (a row that is itself a control cannot contain controls). Renaming
// swaps the title for an inline input with Save / Cancel.
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

const ACTION_CLS =
  "size-5 shrink-0 p-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100";

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
      <li className="flex items-center gap-1 rounded-md bg-primary/5 px-2 py-1.5">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") cancelRename();
          }}
          className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          aria-label={t("chat.history.renameAria")}
        />
        <Button
          variant="ghost"
          size="sm"
          className="size-6 p-0"
          onClick={commitRename}
          aria-label={t("common.save")}
        >
          <Check className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="size-6 p-0"
          onClick={cancelRename}
          aria-label={t("common.cancel")}
        >
          <X className="size-3.5" />
        </Button>
      </li>
    );
  }

  return (
    <li
      className={cn(
        "group flex items-center gap-1 rounded-md pr-1 text-sm transition-colors",
        isActive
          ? "bg-primary/10 text-primary"
          : "text-foreground/80 hover:bg-secondary hover:text-foreground",
      )}
    >
      <button
        type="button"
        className="min-w-0 flex-1 truncate px-2 py-1.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-ring"
        onClick={onSelect}
        aria-current={isActive ? "true" : undefined}
      >
        {conversation.title}
      </button>
      {conversation.channel_binding != null && (
        <span className="shrink-0 rounded-xl border border-transparent bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground">
          {/* The binding stores the channel's uid and the name is resolved at
              read time, so a channel since deleted has no name left. The uid is
              then what the badge says: the conversation really did arrive over
              a channel, and a blank badge would deny it. */}
          {t("chat.history.viaChannel", {
            channel:
              conversation.channel_binding.channel ?? conversation.channel_binding.channel_uid,
          })}
        </span>
      )}
      <span className="flex shrink-0 items-center">
        {onRestore ? (
          <Button
            variant="ghost"
            size="sm"
            className={ACTION_CLS}
            onClick={onRestore}
            aria-label={t("chat.history.restore")}
          >
            <ArchiveRestore className="size-3" />
          </Button>
        ) : (
          <>
            <Button
              variant="ghost"
              size="sm"
              className={ACTION_CLS}
              onClick={() => {
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
                className={ACTION_CLS}
                onClick={onArchive}
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
          className={cn(ACTION_CLS, "hover:text-destructive")}
          onClick={onDelete}
          aria-label={t("chat.history.delete")}
        >
          <Trash2 className="size-3" />
        </Button>
      </span>
    </li>
  );
}
