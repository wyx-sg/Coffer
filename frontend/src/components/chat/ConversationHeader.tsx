// src/components/chat/ConversationHeader.tsx — the open conversation's header:
// its title and where it came from (SourceBadge) on the left; a "⋯" menu of the
// conversation's own commands — Rename, Archive (Unarchive is the button beside it), Delete — on the right.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Archive } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { Conversation } from "@/lib/api/chat";
import { ConversationBackLink } from "./ConversationBackLink";
import { SourceBadge } from "./SourceBadge";

interface Props {
  conversation: Conversation;
  /** The Conversations list the back link returns to, with its filters. */
  listPath: string;
  archived: boolean;
  onRename: (title: string) => void;
  onArchive: () => void;
  onUnarchive: () => void;
  unarchivePending?: boolean;
  onDelete: () => void;
}

export function ConversationHeader({
  conversation,
  listPath,
  archived,
  onRename,
  onArchive,
  onUnarchive,
  unarchivePending = false,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(conversation.title);

  const actions: MenuAction[] = [
    {
      key: "rename",
      label: t("conversations.history.rename"),
      disabled: archived,
      onSelect: () => {
        setDraft(conversation.title);
        setRenaming(true);
      },
    },
    // An archived conversation's Unarchive is the visible button beside the menu.
    ...(archived
      ? []
      : [
          {
            key: "archive",
            label: t("conversations.history.archive"),
            onSelect: onArchive,
          },
        ]),
    {
      key: "delete",
      label: t("conversations.history.delete"),
      destructive: true,
      separated: true,
      onSelect: onDelete,
    },
  ];

  const commit = () => {
    const title = draft.trim();
    if (title && title !== conversation.title) onRename(title);
    setRenaming(false);
  };

  return (
    <div className="flex h-[52px] shrink-0 items-center gap-3 border-b border-border-subtle px-5">
      <ConversationBackLink listPath={listPath} />
      <h1 className="min-w-0 truncate text-md font-semibold text-text">{conversation.title}</h1>
      <SourceBadge conversation={conversation} className="min-w-0 max-w-[16rem] shrink-0" />
      {archived ? (
        <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-md bg-surface-sunken px-1.5 text-2xs font-label text-text-muted">
          <Archive className="size-3" aria-hidden />
          {t("conversations.header.archived")}
        </span>
      ) : null}
      <span className="ml-auto" />
      {archived ? (
        <Button variant="outline" size="sm" onClick={onUnarchive} disabled={unarchivePending}>
          {unarchivePending
            ? t("conversations.archivedThread.unarchiving")
            : t("conversations.history.unarchive")}
        </Button>
      ) : null}
      <ActionMenu label={t("conversations.header.more")} actions={actions} />

      <Dialog open={renaming} onOpenChange={setRenaming}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("conversations.history.renameAria")}</DialogTitle>
          </DialogHeader>
          <form
            id="rename-conversation"
            onSubmit={(e) => {
              e.preventDefault();
              commit();
            }}
          >
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label={t("conversations.history.renameAria")}
            />
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenaming(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" form="rename-conversation" disabled={!draft.trim()}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
