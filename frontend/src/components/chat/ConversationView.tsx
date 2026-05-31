// frontend/src/components/chat/ConversationView.tsx
//
// The right pane: header (title + target + archive/restore action), the
// transcript (persisted history + the live streaming turn), the pending
// confirmation card, and the composer. Switching the `conversationId` resets
// the live-turn overlay so a half-streamed turn never bleeds across rooms.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Archive, ArchiveRestore, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import {
  useArchiveConversation,
  useConversation,
  useRestoreConversation,
} from "@/lib/hooks/useChat";
import { ChatComposer } from "./ChatComposer";
import { ChatMessages } from "./ChatMessages";
import { ConfirmationCard } from "./ConfirmationCard";
import { RenameConversationDialog } from "./RenameConversationDialog";
import { liveTurnMessages, useChatStream } from "./useChatStream";

export function ConversationView({ conversationId }: { conversationId: string }) {
  const { t } = useTranslation();
  const { data, isPending, error, refetch } = useConversation(conversationId);
  const archive = useArchiveConversation();
  const restore = useRestoreConversation();
  const [renameOpen, setRenameOpen] = useState(false);

  const stream = useChatStream(conversationId, () => void refetch());

  // Reset the live-turn overlay whenever we switch conversations.
  useEffect(() => {
    stream.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  if (isPending) {
    return (
      <div className="grid flex-1 place-items-center text-sm text-muted-foreground">
        {t("common.loading")}
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="grid flex-1 place-items-center px-6 text-center text-sm text-destructive">
        {error ? translateApiError(t, error) : t("chat.loadFailed")}
      </div>
    );
  }

  const { conversation } = data;
  const archived = conversation.status === "archived";
  const title = conversation.title?.trim() || t("chat.untitled");
  const messages = [...data.messages, ...liveTurnMessages(stream.state)];

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-foreground">{title}</h2>
          <p className="truncate text-xs text-muted-foreground">{conversation.target_ref}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setRenameOpen(true)}
            aria-label={t("chat.actions.rename")}
          >
            <Pencil className="size-4" />
          </Button>
          {archived ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => restore.mutate(conversation.id)}
              aria-label={t("chat.actions.restore")}
            >
              <ArchiveRestore className="size-4" /> {t("chat.actions.restore")}
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => archive.mutate(conversation.id)}
              aria-label={t("chat.actions.archive")}
            >
              <Archive className="size-4" /> {t("chat.actions.archive")}
            </Button>
          )}
        </div>
      </header>

      <ChatMessages
        messages={messages}
        confirmationCard={
          stream.state.confirmation ? (
            <ConfirmationCard
              confirmation={stream.state.confirmation}
              onApprove={() => void stream.confirm(true)}
              onDeny={() => void stream.confirm(false)}
            />
          ) : null
        }
      />

      <ChatComposer
        streaming={stream.state.streaming}
        disabled={archived}
        onSend={(text) => void stream.send(text)}
        onStop={() => void stream.stop()}
      />

      <RenameConversationDialog
        id={conversation.id}
        currentTitle={conversation.title ?? ""}
        open={renameOpen}
        onOpenChange={setRenameOpen}
      />
    </div>
  );
}
