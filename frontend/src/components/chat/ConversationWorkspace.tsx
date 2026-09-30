// src/components/chat/ConversationWorkspace.tsx — an open conversation (or the
// draft) beside the list it was opened from: a resizable split (SplitView, width
// remembered as `coffer.split.chat.list`), the list collapsed below `md` where
// two panes would leave the thread unreadable. The right pane is the thread with
// its header and reply box, the draft, a loading line, or — for a link to a
// conversation that no longer exists — a notice with a way to start a new one.
import { useTranslation } from "react-i18next";
import { MessageSquareOff } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { SplitView } from "@/components/SplitView";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { ChatController } from "@/lib/hooks/useChatController";
import { useMediaQuery } from "@/lib/hooks/useMediaQuery";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { ConversationHeader } from "./ConversationHeader";
import { ConversationList } from "./ConversationList";
import { DraftThread } from "./DraftThread";
import { MessageThread } from "./MessageThread";

// Wide enough for a title beside its time, and the source badge under it.
const LIST_DEFAULT_WIDTH = 280;

interface Props {
  c: ChatController;
  onNew: () => void;
  agentNames: ReadonlyMap<string, string>;
}

export function ConversationWorkspace({ c, onNew, agentNames }: Props) {
  const { t } = useTranslation();
  const isDesktop = useMediaQuery("(min-width: 768px)", true);
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
            agentLabel={agentLabel}
            archived={c.activeArchived}
            onRename={(title) => c.renameConversation(conv.id, title)}
            onArchive={() => c.requestArchive(conv.id)}
            onRestore={() => c.restoreConversation(conv.id)}
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
        readOnly={c.activeArchived}
        onRestore={() => c.restoreConversation(conv.id)}
        restorePending={c.restorePending}
      />
    );
  } else if (c.activeLoading) {
    detail = (
      <p className="flex flex-1 items-center justify-center text-sm text-text-muted">
        {t("common.loading")}
      </p>
    );
  } else if (c.activeNotFound) {
    // A stale deep link says so rather than dropping silently into a draft.
    detail = (
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
    );
  } else {
    detail = (
      <DraftThread
        agents={c.agents}
        agentKey={c.effectiveDraft.agentKey}
        cwd={c.effectiveDraft.cwd}
        noManagedAgent={c.noManagedAgent}
        onAgentChange={c.setDraftAgent}
        modelValue={c.effectiveDraft.model}
        onModelChange={c.setDraftModel}
        effortValue={c.effectiveDraft.effort}
        onEffortChange={c.setDraftEffort}
        onSend={c.sendDraft}
        creating={c.creating}
      />
    );
  }

  return (
    <SplitView
      storageKey="chat.list"
      defaultListWidth={LIST_DEFAULT_WIDTH}
      label={t("splitView.resizeList")}
      listHidden={!isDesktop}
      className="h-full flex-1"
      listClassName="bg-surface-sidebar"
      detailClassName="flex flex-col overflow-hidden"
      list={
        <ConversationList
          conversations={c.listConversations}
          activeId={conv?.id ?? null}
          loading={c.listLoading}
          listPath={c.listPath}
          hrefFor={c.pathFor}
          agentNames={agentNames}
          onCreate={onNew}
        />
      }
      detail={
        <>
          {c.createError ? (
            <ChatErrorBanner
              className="border-b"
              message={translateApiError(t, c.createError)}
              onDismiss={c.resetCreateError}
            />
          ) : null}
          {detail}
        </>
      }
    />
  );
}
