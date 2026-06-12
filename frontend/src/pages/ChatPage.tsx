// pages/ChatPage.tsx — 3-column chat layout (presentational).
// Column 1 = app sidebar (Layout.tsx); column 2 = collapsible history; column 3
// = the open conversation's thread, or the draft surface when none is open.
// Orchestration lives in useChatController; the open conversation is the URL
// (/chat/:id), so refresh and deep-links reopen the same thread.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useChatController } from "@/lib/hooks/useChatController";
import { ConversationList } from "@/components/chat/ConversationList";
import { MessageThread } from "@/components/chat/MessageThread";
import { DraftThread } from "@/components/chat/DraftThread";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

export function ChatPage() {
  const { t } = useTranslation();
  const [historyOpen, setHistoryOpen] = useState(true);
  const c = useChatController();

  return (
    <div className="relative -mx-6 -my-10 flex h-screen overflow-hidden md:-mx-10">
      {/* History column */}
      <div
        className={cn(
          "flex-col border-r border-border bg-card/30 transition-all duration-200",
          historyOpen ? "flex w-64" : "hidden w-0",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-2 py-2">
          <span className="px-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("chat.title")}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="size-7 p-0"
            onClick={() => setHistoryOpen(false)}
            aria-label={t("chat.history.collapse")}
          >
            <PanelLeftClose className="size-4" />
          </Button>
        </div>
        <ConversationList
          conversations={c.listConversations}
          activeId={c.activeConv?.id ?? null}
          loading={c.listLoading}
          view={c.showArchived ? "archived" : "active"}
          onToggleView={c.toggleView}
          onSelect={c.selectConversation}
          onCreate={c.startDraft}
          onRename={c.renameConversation}
          onDelete={c.requestDelete}
          onArchive={c.requestArchive}
          onRestore={c.restoreConversation}
        />
      </div>

      {/* Thread column */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {!historyOpen && (
          <div className="border-b border-border px-2 py-2">
            <Button
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              onClick={() => setHistoryOpen(true)}
              aria-label={t("chat.history.expand")}
            >
              <PanelLeftOpen className="size-4" />
            </Button>
          </div>
        )}

        {c.activeConv ? (
          <MessageThread
            conversation={c.activeConv}
            models={c.models}
            liveMessage={c.turn.liveMessage}
            isStreaming={c.turn.isStreaming}
            turnError={c.turn.error}
            pendingApproval={c.turn.pendingApproval}
            onApprovalDecide={c.turn.submitApproval}
            onStop={() => void c.turn.interrupt()}
            onSend={(text) => {
              c.turn.clearError();
              c.turn.send(text);
            }}
            onClearTurnError={c.turn.clearError}
            onModelChange={(modelId) => c.setConversationModel(c.activeConv!.id, modelId)}
            agentLabel={c.activeAgent?.display_name ?? c.activeConv.agent_key}
            showModelSelector={c.activeConv.agent_key === "builtin"}
          />
        ) : (
          <DraftThread
            agents={c.agents}
            models={c.models}
            agentKey={c.effectiveDraft.agentKey}
            modelId={c.effectiveDraft.modelId}
            onAgentChange={c.setDraftAgent}
            onModelChange={c.setDraftModel}
            onSend={c.sendDraft}
            creating={c.creating}
          />
        )}
      </div>

      {c.createError && (
        <div
          role="alert"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive shadow-md"
        >
          <span className="flex-1">{translateApiError(t, c.createError)}</span>
          <button
            type="button"
            className="ml-3 font-medium underline-offset-2 hover:underline"
            onClick={c.resetCreateError}
          >
            {t("common.dismiss")}
          </button>
        </div>
      )}

      <ConfirmDialog
        open={c.deletingId !== null}
        onOpenChange={(o) => !o && c.requestDelete(null)}
        title={t("chat.delete.title")}
        description={t("chat.delete.body")}
        confirmLabel={c.deletePending ? t("common.deleting") : t("common.delete")}
        pending={c.deletePending}
        onConfirm={c.confirmDelete}
      />

      <ConfirmDialog
        open={c.archivingId !== null}
        onOpenChange={(o) => !o && c.requestArchive(null)}
        title={t("chat.archive.title")}
        description={t("chat.archive.body")}
        confirmLabel={t("chat.archive.confirm")}
        variant="default"
        pending={c.archivePending}
        onConfirm={c.confirmArchive}
      />
    </div>
  );
}
