// src/components/chat/ConversationWorkspace.tsx — an open conversation (or the
// draft), full width: no list beside it — the header's back link returns to the
// list (ConversationBackLink). It is the thread with its header and reply box,
// the draft, a loading line, or — for a link to a conversation that no longer
// exists — a notice with a way back and a way to start a new one.
import { useTranslation } from "react-i18next";
import { MessageSquareOff } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { ChatController } from "@/lib/hooks/useChatController";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { ConversationHeader } from "./ConversationHeader";
import { ConversationBackLink } from "./ConversationBackLink";
import { DraftThread } from "./DraftThread";
import { MessageThread } from "./MessageThread";

interface Props {
  c: ChatController;
  onNew: () => void;
  agentNames: ReadonlyMap<string, string>;
}

/** A header strip holding only the back link (loading, not-found). */
function BackBar({ listPath }: { listPath: string }) {
  return (
    <div className="flex h-[52px] shrink-0 items-center border-b border-border-subtle px-5">
      <ConversationBackLink listPath={listPath} />
    </div>
  );
}

export function ConversationWorkspace({ c, onNew, agentNames }: Props) {
  const { t } = useTranslation();
  const conv = c.activeConv;
  const agentLabel = conv ? (c.activeAgent?.display_name ?? agentNames.get(conv.agent_key)) : "";

  let detail: JSX.Element;
  if (conv) {
    detail = (
      <MessageThread
        conversation={conv}
        header={
          <ConversationHeader
            conversation={conv}
            listPath={c.listPath}
            archived={c.activeArchived}
            onRename={(title) => c.renameConversation(conv.id, title)}
            onArchive={() => c.archiveConversation(conv.id)}
            onUnarchive={() => c.unarchiveConversation(conv.id)}
            unarchivePending={c.unarchivePending}
            onDelete={() => c.requestDelete(conv.id)}
          />
        }
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
    );
  } else if (c.activeLoading) {
    detail = (
      <>
        <BackBar listPath={c.listPath} />
        <p className="flex flex-1 items-center justify-center text-sm text-text-muted">
          {t("common.loading")}
        </p>
      </>
    );
  } else if (c.activeNotFound) {
    // A stale deep link says so rather than dropping silently into a draft.
    detail = (
      <>
        <BackBar listPath={c.listPath} />
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
        listPath={c.listPath}
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
