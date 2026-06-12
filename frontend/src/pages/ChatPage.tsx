// pages/ChatPage.tsx — 3-column chat layout.
// Column 1 = app sidebar (provided by Layout.tsx)
// Column 2 = collapsible conversation history
// Column 3 = message thread
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useConversations,
  useCreateConversation,
  useRenameConversation,
  useDeleteConversation,
  useSetConversationModel,
} from "@/lib/hooks/useConversations";
import { useModels } from "@/lib/hooks/useModels";
import { useChatAgents } from "@/lib/hooks/useChatAgents";
import { useChatTurn } from "@/lib/hooks/useChatTurn";
import { ConversationList } from "@/components/chat/ConversationList";
import { MessageThread } from "@/components/chat/MessageThread";
import { NewConversationDialog } from "@/components/chat/NewConversationDialog";
import type { ConversationCreate } from "@/lib/api/chat";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

export function ChatPage() {
  const { t } = useTranslation();
  const [historyOpen, setHistoryOpen] = useState(true);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: conversations = [], isPending: convLoading } = useConversations();
  const { data: models = [] } = useModels();
  const { data: agents = [] } = useChatAgents();
  const createConv = useCreateConversation();
  const renameConv = useRenameConversation();
  const deleteConv = useDeleteConversation();
  const setModel = useSetConversationModel();

  const activeConv = conversations.find((c) => c.id === activeConvId) ?? null;
  const activeAgent = activeConv
    ? agents.find((a) => a.agent_key === activeConv.agent_key)
    : undefined;

  const {
    send,
    isStreaming,
    liveMessage,
    error: turnError,
    clearError,
    pendingApproval,
    submitApproval,
    interrupt,
  } = useChatTurn(activeConvId ?? "");

  const handleCreate = (body: ConversationCreate) => {
    // Use mutate (not mutateAsync) so a rejected create routes to the
    // mutation's error state instead of an unhandled promise rejection; the
    // failure is then surfaced in the banner below.
    createConv.mutate(body, {
      onSuccess: (created) => setActiveConvId(created.id),
    });
  };

  const handleDelete = (id: string) => {
    deleteConv.mutate(id);
    if (activeConvId === id) setActiveConvId(null);
  };

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
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1">
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
          conversations={conversations}
          activeId={activeConvId}
          loading={convLoading}
          onSelect={setActiveConvId}
          onCreate={() => setDialogOpen(true)}
          onRename={(id, title) => renameConv.mutate({ id, title })}
          onDelete={handleDelete}
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

        {activeConv ? (
          <MessageThread
            conversation={activeConv}
            models={models}
            liveMessage={liveMessage}
            isStreaming={isStreaming}
            turnError={turnError}
            pendingApproval={pendingApproval}
            onApprovalDecide={submitApproval}
            onStop={() => void interrupt()}
            onSend={(text) => {
              clearError();
              send(text);
            }}
            onClearTurnError={clearError}
            onModelChange={(modelId) =>
              setModel.mutate({ id: activeConv.id, model_id: modelId })
            }
            agentLabel={activeAgent?.display_name ?? activeConv.agent_key}
            showModelSelector={activeConv.agent_key === "builtin"}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-12 text-center">
            <p className="text-sm text-muted-foreground">
              {t("chat.thread.selectOrCreate")}
            </p>
            <Button onClick={() => setDialogOpen(true)}>
              {t("chat.history.new")}
            </Button>
          </div>
        )}
      </div>

      {createConv.isError && (
        <div
          role="alert"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive shadow-md"
        >
          <span className="flex-1">{translateApiError(t, createConv.error)}</span>
          <button
            type="button"
            className="ml-3 font-medium underline-offset-2 hover:underline"
            onClick={() => createConv.reset()}
          >
            {t("common.dismiss")}
          </button>
        </div>
      )}

      <NewConversationDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        agents={agents}
        models={models}
        onCreate={handleCreate}
      />
    </div>
  );
}
