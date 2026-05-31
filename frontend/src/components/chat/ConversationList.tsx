// frontend/src/components/chat/ConversationList.tsx
//
// The left rail: a status filter (active / archived), a New-chat button, and
// the list of conversations. Each row links to /chat/:id and carries an action
// menu (rename / archive · restore / delete).
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Archive, ArchiveRestore, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ConversationOut, ConversationStatus } from "@/lib/api/chat";
import {
  useArchiveConversation,
  useDeleteConversation,
  useRestoreConversation,
} from "@/lib/hooks/useChat";
import { cn } from "@/lib/utils";
import { RenameConversationDialog } from "./RenameConversationDialog";

export function ConversationList({
  conversations,
  activeId,
  statusFilter,
  isPending,
  onStatusChange,
  onNew,
  onDeleted,
}: {
  conversations: ConversationOut[];
  activeId?: string;
  statusFilter: ConversationStatus;
  isPending: boolean;
  onStatusChange: (status: ConversationStatus) => void;
  onNew: () => void;
  /** Called after a delete so the parent can navigate off a removed conversation. */
  onDeleted: (id: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-border">
      <div className="flex items-center justify-between gap-2 border-b border-border p-3">
        <div className="flex rounded-md bg-secondary p-0.5 text-xs">
          {(["active", "archived"] as const).map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => onStatusChange(status)}
              className={cn(
                "rounded px-2.5 py-1 font-medium transition-colors",
                statusFilter === status
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {status === "active" ? t("chat.filter.active") : t("chat.filter.archived")}
            </button>
          ))}
        </div>
        <Button size="sm" onClick={onNew} aria-label={t("chat.new.button")}>
          <Plus className="size-4" />
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {isPending ? (
          <p className="p-4 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : conversations.length === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">
            {statusFilter === "archived" ? t("chat.list.emptyArchived") : t("chat.list.empty")}
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((conv) => (
              <ConversationRow
                key={conv.id}
                conversation={conv}
                active={conv.id === activeId}
                onDeleted={onDeleted}
              />
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}

function ConversationRow({
  conversation,
  active,
  onDeleted,
}: {
  conversation: ConversationOut;
  active: boolean;
  onDeleted: (id: string) => void;
}) {
  const { t } = useTranslation();
  const archive = useArchiveConversation();
  const restore = useRestoreConversation();
  const del = useDeleteConversation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

  const title = conversation.title?.trim() || t("chat.untitled");

  const handleDelete = () => {
    setMenuOpen(false);
    del.mutate(conversation.id, { onSuccess: () => onDeleted(conversation.id) });
  };

  return (
    <li className="group relative">
      <Link
        to={`/chat/${conversation.id}`}
        className={cn(
          "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
          active
            ? "bg-primary/10 text-primary"
            : "text-foreground/80 hover:bg-secondary hover:text-foreground",
        )}
      >
        <span className="flex-1 truncate">{title}</span>
      </Link>
      <Popover open={menuOpen} onOpenChange={setMenuOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={t("chat.actions.menu")}
            className={cn(
              "absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground transition-colors hover:bg-background hover:text-foreground",
              menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100",
            )}
          >
            <MoreVertical className="size-4" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-44 p-1">
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              setRenameOpen(true);
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-secondary"
          >
            <Pencil className="size-4" /> {t("chat.actions.rename")}
          </button>
          {conversation.status === "active" ? (
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                archive.mutate(conversation.id);
              }}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-secondary"
            >
              <Archive className="size-4" /> {t("chat.actions.archive")}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                restore.mutate(conversation.id);
              }}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-secondary"
            >
              <ArchiveRestore className="size-4" /> {t("chat.actions.restore")}
            </button>
          )}
          <button
            type="button"
            onClick={handleDelete}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm text-destructive hover:bg-secondary"
          >
            <Trash2 className="size-4" /> {t("chat.actions.delete")}
          </button>
        </PopoverContent>
      </Popover>

      <RenameConversationDialog
        id={conversation.id}
        currentTitle={conversation.title ?? ""}
        open={renameOpen}
        onOpenChange={setRenameOpen}
      />
    </li>
  );
}
