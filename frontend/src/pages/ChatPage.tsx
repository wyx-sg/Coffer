// pages/ChatPage.tsx — 3-column chat layout.
// Column 1 = app sidebar (provided by Layout.tsx)
// Column 2 = collapsible conversation history
// Column 3 = message thread, or the draft surface when no conversation is open
//
// The open conversation is the URL (`/chat/:id`), not local state, so a refresh
// or deep-link reopens the same thread. `/chat` with no id is the draft: the
// first message sent there creates the conversation, then we navigate to it.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
import { DraftThread } from "@/components/chat/DraftThread";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

export function ChatPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: routeId } = useParams<{ id?: string }>();
  const [historyOpen, setHistoryOpen] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Draft top-bar selection (agent + model) before the conversation exists.
  // null until the user touches a selector — defaults are derived below.
  const [draftConfig, setDraftConfig] = useState<{ agentKey: string; modelId: string | null } | null>(
    null,
  );
  // After creating from the draft, the first message is sent once the turn hook
  // re-binds to the new conversation id (see effect below).
  const [pendingFirst, setPendingFirst] = useState<{ convId: string; text: string } | null>(null);

  const { data: conversations = [], isPending: convLoading } = useConversations();
  const { data: models = [] } = useModels();
  const { data: agents = [] } = useChatAgents();
  const createConv = useCreateConversation();
  const renameConv = useRenameConversation();
  const deleteConv = useDeleteConversation();
  const setModel = useSetConversationModel();

  const activeConv = conversations.find((c) => c.id === routeId) ?? null;
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
  } = useChatTurn(activeConv?.id ?? "");

  // Once navigation has bound the turn hook to the freshly-created conversation,
  // fire its first message. Gated on the id matching so it never sends to the
  // wrong thread.
  useEffect(() => {
    if (pendingFirst && activeConv?.id === pendingFirst.convId) {
      const text = pendingFirst.text;
      setPendingFirst(null);
      void send(text);
    }
  }, [pendingFirst, activeConv?.id, send]);

  const defaultModelId = models.find((m) => m.is_default)?.id ?? models[0]?.id ?? null;
  const effectiveDraft = draftConfig ?? {
    agentKey: agents.find((a) => a.available)?.agent_key ?? "builtin",
    modelId: defaultModelId,
  };

  const startDraft = () => {
    setDraftConfig({ agentKey: effectiveDraft.agentKey, modelId: defaultModelId });
    navigate("/chat");
  };

  const handleSelect = (id: string) => {
    setDraftConfig(null);
    navigate(`/chat/${id}`);
  };

  const handleDraftSend = (text: string) => {
    createConv.mutate(
      {
        agent_key: effectiveDraft.agentKey,
        agent_config: effectiveDraft.modelId ? { model_id: effectiveDraft.modelId } : {},
      },
      {
        onSuccess: (created) => {
          setPendingFirst({ convId: created.id, text });
          setDraftConfig(null);
          navigate(`/chat/${created.id}`);
        },
      },
    );
  };

  const confirmDelete = () => {
    if (!deletingId) return;
    const id = deletingId;
    deleteConv.mutate(id, {
      onSuccess: () => {
        setDeletingId(null);
        if (routeId === id) navigate("/chat");
      },
    });
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
          activeId={activeConv?.id ?? null}
          loading={convLoading}
          onSelect={handleSelect}
          onCreate={startDraft}
          onRename={(id, title) => renameConv.mutate({ id, title })}
          onDelete={(id) => setDeletingId(id)}
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
          <DraftThread
            agents={agents}
            models={models}
            agentKey={effectiveDraft.agentKey}
            modelId={effectiveDraft.modelId}
            onAgentChange={(agentKey) =>
              setDraftConfig({ agentKey, modelId: effectiveDraft.modelId })
            }
            onModelChange={(modelId) =>
              setDraftConfig({ agentKey: effectiveDraft.agentKey, modelId })
            }
            onSend={handleDraftSend}
            creating={createConv.isPending}
          />
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

      <ConfirmDialog
        open={deletingId !== null}
        onOpenChange={(o) => !o && setDeletingId(null)}
        title={t("chat.delete.title")}
        description={t("chat.delete.body")}
        confirmLabel={deleteConv.isPending ? t("common.deleting") : t("common.delete")}
        pending={deleteConv.isPending}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
