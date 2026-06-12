// src/lib/hooks/useChatController.ts
// Orchestration for the Chat page: binds the conversation/model/agent queries,
// the streaming turn, and the draft → create → first-message flow, exposing a
// flat interface the ChatPage component renders. Keeping this out of the page
// keeps the component presentational (and under the file-size limit).
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

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

export function useChatController() {
  const navigate = useNavigate();
  const { id: routeId } = useParams<{ id?: string }>();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Draft top-bar selection (agent + model) before the conversation exists;
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

  const turn = useChatTurn(activeConv?.id ?? "");

  // Once navigation has bound the turn hook to the freshly-created conversation,
  // fire its first message. Gated on the id matching so it never sends to the
  // wrong thread.
  useEffect(() => {
    if (pendingFirst && activeConv?.id === pendingFirst.convId) {
      const text = pendingFirst.text;
      setPendingFirst(null);
      void turn.send(text);
    }
  }, [pendingFirst, activeConv?.id, turn]);

  const defaultModelId = models.find((m) => m.is_default)?.id ?? models[0]?.id ?? null;
  const effectiveDraft = draftConfig ?? {
    agentKey: agents.find((a) => a.available)?.agent_key ?? "builtin",
    modelId: defaultModelId,
  };

  const startDraft = () => {
    setDraftConfig({ agentKey: effectiveDraft.agentKey, modelId: defaultModelId });
    navigate("/chat");
  };

  const selectConversation = (id: string) => {
    setDraftConfig(null);
    navigate(`/chat/${id}`);
  };

  const sendDraft = (text: string) => {
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

  return {
    conversations,
    convLoading,
    models,
    agents,
    activeConv,
    activeAgent,
    turn,
    effectiveDraft,
    setDraftAgent: (agentKey: string) =>
      setDraftConfig({ agentKey, modelId: effectiveDraft.modelId }),
    setDraftModel: (modelId: string | null) =>
      setDraftConfig({ agentKey: effectiveDraft.agentKey, modelId }),
    startDraft,
    selectConversation,
    sendDraft,
    creating: createConv.isPending,
    createError: createConv.isError ? createConv.error : null,
    resetCreateError: () => createConv.reset(),
    renameConversation: (id: string, title: string) => renameConv.mutate({ id, title }),
    setConversationModel: (id: string, modelId: string | null) =>
      setModel.mutate({ id, model_id: modelId }),
    deletingId,
    requestDelete: setDeletingId,
    confirmDelete,
    deletePending: deleteConv.isPending,
  };
}
