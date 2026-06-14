// pages/ChatPage.tsx — 2-column chat layout (presentational).
// Column 1 = app sidebar (Layout.tsx); column 2 = collapsible conversation list;
// column 3 = the open conversation's thread, or the draft surface when none is
// open. Orchestration lives in useChatController; the open conversation is the
// URL (/chat/:id), so refresh and deep-links reopen the same thread.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquareOff, PanelLeftClose, PanelLeftOpen } from "lucide-react";
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
      {/* Conversation-list column */}
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
            agentLabel={c.activeAgent?.display_name ?? c.activeConv.agent_key}
            readOnly={c.activeArchived}
            onRestore={() => c.restoreConversation(c.activeConv!.id)}
            restorePending={c.restorePending}
          />
        ) : c.activeLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          </div>
        ) : c.activeNotFound ? (
          // A stale deep-link or deleted conversation: say so explicitly
          // instead of silently dropping into the draft surface.
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-12 text-center">
            <MessageSquareOff
              className="size-12 text-muted-foreground/40"
              strokeWidth={1.25}
              aria-hidden
            />
            <div className="space-y-1">
              <h2 className="text-lg font-semibold">{t("chat.thread.notFoundTitle")}</h2>
              <p className="max-w-xs text-sm text-muted-foreground">
                {t("chat.thread.notFoundBody")}
              </p>
            </div>
            <Button variant="outline" onClick={c.startDraft}>
              {t("chat.thread.notFoundCta")}
            </Button>
          </div>
        ) : (
          <DraftThread
            agents={c.agents}
            agentKey={c.effectiveDraft.agentKey}
            cwd={c.effectiveDraft.cwd}
            recentCwds={c.recentCwds}
            noManagedAgent={c.noManagedAgent}
            onAgentChange={c.setDraftAgent}
            onCwdChange={c.setDraftCwd}
            onSend={c.sendDraft}
            creating={c.creating}
          />
        )}
      </div>

      {c.createError ? (
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
      ) : null}

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
