// src/components/chat/ConversationWorkspace.tsx — an open conversation (or the
// draft), full width: no list beside it. It is the title row (in the window
// title bar) over the thread and its reply box, the draft, a loading line, or —
// for a link to a conversation that no longer exists — a notice with a way to
// start a new one.
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { MessageSquareOff } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { ChatController } from "@/lib/hooks/useChatController";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { ConversationHeader } from "./ConversationHeader";
import { DraftThread } from "./DraftThread";
import { MessageThread } from "./MessageThread";

interface Props {
  c: ChatController;
  onNew: () => void;
  agentNames: ReadonlyMap<string, string>;
}

export function ConversationWorkspace({ c, onNew, agentNames }: Props) {
  const { t } = useTranslation();
  const conv = c.activeConv;
  const navigate = useNavigate();
  const { pathname, search, state } = useLocation();
  // The list's Rename opens the conversation with its title already being edited.
  const renameRequested = (state as { rename?: boolean } | null)?.rename === true;
  useEffect(() => {
    if (renameRequested && conv) navigate(`${pathname}${search}`, { replace: true, state: null });
  }, [renameRequested, conv, pathname, search, navigate]);
  const agentLabel = conv ? (c.activeAgent?.display_name ?? agentNames.get(conv.agent_key)) : "";

  let detail: JSX.Element;
  if (conv) {
    detail = (
      <>
        <ConversationHeader
          key={conv.id}
          conversation={conv}
          archived={c.activeArchived}
          startRenaming={renameRequested}
          onRename={(title) => c.renameConversation(conv.id, title)}
          onArchive={() => c.archiveConversation(conv.id)}
          onDelete={() => c.requestDelete(conv.id)}
        />
        <MessageThread
          conversation={conv}
          agentLabel={agentLabel}
          liveMessage={c.turn.liveMessage}
          pendingEchoes={c.turn.pendingEchoes}
          isStreaming={c.turn.isStreaming}
          turnError={c.turn.error}
          streamLost={c.turn.streamLost}
          onReload={c.turn.reload}
          onStop={() => void c.turn.interrupt()}
          onSend={(text, attachments) => {
            c.turn.clearError();
            return c.turn.send(text, attachments);
          }}
          onClearTurnError={c.turn.clearError}
          retryable={c.turn.retryable}
          restore={c.refusedFirst}
          onRestored={c.clearRefusedFirst}
          onResend={c.turn.resend}
          pending={c.turn.pending}
          onSetPending={(texts) => void c.turn.setPending(texts)}
          queueHeld={c.turn.queueHeld}
          onResumeQueue={() => void c.turn.resumeQueue()}
          readOnly={c.activeArchived}
          onUnarchive={() => c.unarchiveConversation(conv.id)}
          unarchivePending={c.unarchivePending}
        />
      </>
    );
  } else if (c.activeLoading) {
    detail = (
      <>
        <p className="flex flex-1 items-center justify-center text-sm text-text-muted">
          {t("common.loading")}
        </p>
      </>
    );
  } else if (c.activeNotFound) {
    // A stale deep link says so rather than dropping silently into a draft.
    detail = (
      <>
        <EmptyState
          className="flex-1"
          icon={MessageSquareOff}
          title={t("conversations.thread.notFoundTitle")}
          description={t("conversations.thread.notFoundBody")}
          action={
            <Button variant="outline" onClick={onNew}>
              {t("conversations.thread.notFoundCta")}
            </Button>
          }
        />
      </>
    );
  } else {
    detail = (
      <DraftThread
        agents={c.agents}
        agentKey={c.effectiveDraft.agentKey}
        cwd={c.effectiveDraft.cwd}
        noManagedAgent={c.noManagedAgent}
        onAgentChange={c.setDraftAgent}
        onCwdChange={c.setDraftCwd}
        modelValue={c.effectiveDraft.model}
        onModelChange={c.setDraftModel}
        effortValue={c.effectiveDraft.effort}
        onEffortChange={c.setDraftEffort}
        onSend={c.sendDraft}
        creating={c.creating}
        restore={c.draftPrefill}
        onRestored={c.clearDraftPrefill}
        fromHandoff={c.draftFromHandoff}
      />
    );
  }

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      {c.createError ? (
        <ChatErrorBanner
          className="border-b"
          message={translateApiError(t, c.createError)}
          onDismiss={c.resetCreateError}
        />
      ) : null}
      {detail}
    </div>
  );
}
