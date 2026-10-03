// src/components/chat/ConversationHeader.tsx — the open conversation's title row.
//
// It is the one page content that lives in the window title bar (InTitleBar;
// in a browser tab it is a 44px bar at the top of the content): the title,
// where a channel conversation came from — with "Replies stay in Coffer" and
// its reason when a reply cannot go back to the chat (spec chat "Show where a
// reply will also be sent") — and a ⋯ menu of the conversation's own commands:
// Rename, Archive, Delete (an archived one's Unarchive is in its notice). Rename
// turns the title into an input in place: Enter saves, Esc cancels.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { PlatformMark } from "@/components/channel/PlatformMark";
import { HelpTip } from "@/components/HelpTip";
import { InTitleBar } from "@/components/shell/titleBarSlot";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { TruncatedText } from "@/components/ui/truncated-text";
import type { Conversation } from "@/lib/api/chat";
import { sourceText } from "@/lib/conversations/sourceText";
import { useChannelMirror } from "@/lib/hooks/useConversations";

/** The reasons the daemon gives for a reply that stays in Coffer. */
const REASONS = new Set(["group_main", "not_located", "chat_kind_unknown", "channel_deleted"]);
const NO_MESSAGES: never[] = [];

interface Props {
  conversation: Conversation;
  archived: boolean;
  /** Open with the title already being edited (the list's Rename). */
  startRenaming?: boolean;
  onRename: (title: string) => void;
  onArchive: () => void;
  onDelete: () => void;
}

function Source({ conversation }: { conversation: Conversation }) {
  const { t } = useTranslation();
  const { mirror } = useChannelMirror(conversation, NO_MESSAGES);
  const binding = conversation.channel_binding;
  if (!binding) return null;
  const reason = mirror?.reason && REASONS.has(mirror.reason) ? mirror.reason : "not_located";
  return (
    <>
      <span
        data-testid="conversation-source"
        className="inline-flex min-w-0 items-center gap-1.5 whitespace-nowrap text-xs text-text-muted"
      >
        <PlatformMark platform={binding.platform ?? "channel"} />
        <span className="truncate">{sourceText(t, conversation)}</span>
      </span>
      {mirror && !mirror.deliverable ? (
        <span className="inline-flex shrink-0 items-center gap-0.5 whitespace-nowrap text-xs text-text-muted">
          {t("conversations.mirror.staysInCoffer")}
          <HelpTip>
            <p className="text-sm">{t(`conversations.mirror.reason.${reason}`)}</p>
          </HelpTip>
        </span>
      ) : null}
    </>
  );
}

export function ConversationHeader({
  conversation,
  archived,
  startRenaming = false,
  onRename,
  onArchive,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const [renaming, setRenaming] = useState(startRenaming && !archived);
  const [draft, setDraft] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);

  const beginRename = () => {
    if (archived) return;
    setDraft(conversation.title);
    setRenaming(true);
  };
  useEffect(() => {
    if (renaming) inputRef.current?.select();
  }, [renaming]);

  const commit = () => {
    const title = draft.trim();
    if (title && title !== conversation.title) onRename(title);
    setRenaming(false);
  };

  const actions: MenuAction[] = [
    {
      key: "rename",
      label: t("conversations.history.rename"),
      disabled: archived,
      onSelect: beginRename,
    },
    ...(archived
      ? []
      : [{ key: "archive", label: t("conversations.history.archive"), onSelect: onArchive }]),
    {
      key: "delete",
      label: t("conversations.history.delete"),
      destructive: true,
      separated: true,
      onSelect: onDelete,
    },
  ];

  return (
    <InTitleBar>
      {renaming ? (
        <>
          <input
            ref={inputRef}
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return;
              if (e.key === "Enter") {
                e.preventDefault();
                commit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                setRenaming(false);
              }
            }}
            onBlur={() => setRenaming(false)}
            aria-label={t("conversations.header.titleAria")}
            className="h-7 w-[420px] min-w-0 max-w-full shrink rounded-md border border-accent bg-surface-raised px-2 text-sm font-semibold text-text shadow-focus outline-none"
          />
          <span className="shrink-0 whitespace-nowrap text-xs text-text-muted">
            {t("conversations.header.renameHint")}
          </span>
        </>
      ) : (
        <>
          <h1 className="min-w-0 shrink text-sm font-semibold text-text">
            <button
              type="button"
              onClick={beginRename}
              disabled={archived}
              className="block max-w-full min-w-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:cursor-default"
            >
              <TruncatedText text={conversation.title} />
            </button>
          </h1>
          <Source conversation={conversation} />
        </>
      )}
      <span className="ml-auto shrink-0">
        <ActionMenu label={t("conversations.header.more")} actions={actions} />
      </span>
    </InTitleBar>
  );
}

/** The title row of the draft (`/conversations/new`) and of the no-agent state: just the name, no menu. */
export function DraftTitleBar() {
  const { t } = useTranslation();
  return (
    <InTitleBar>
      <h1 className="text-sm font-semibold text-text">{t("conversations.new.title")}</h1>
    </InTitleBar>
  );
}
