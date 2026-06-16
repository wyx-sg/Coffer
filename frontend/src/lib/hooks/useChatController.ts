// src/lib/hooks/useChatController.ts
// Orchestration for the Chat page: binds the conversation/agent queries, the
// streaming turn, and the draft → create → first-message flow, exposing a flat
// interface the ChatPage component renders. Keeping this out of the page keeps
// the component presentational (and under the file-size limit).
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  useConversations,
  useArchivedConversations,
  useConversation,
  useCreateConversation,
  useRenameConversation,
  useDeleteConversation,
  useArchiveConversation,
  useUnarchiveConversation,
} from "@/lib/hooks/useConversations";
import { useChatAgents } from "@/lib/hooks/useChatAgents";
import { useChatTurn } from "@/lib/hooks/useChatTurn";

export function useChatController() {
  const navigate = useNavigate();
  const { id: routeId } = useParams<{ id?: string }>();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  // Draft top-bar selection (the agent) before the conversation exists; null
  // until the user touches the selector — the default is derived below. There
  // is no per-turn working-directory choice anymore: a turn runs in the
  // Coffer-managed workspace (~/.coffer/workspace) by default.
  const [draftConfig, setDraftConfig] = useState<{ agentKey: string } | null>(null);
  // After creating from the draft, the first message is sent once the turn hook
  // re-binds to the new conversation id (see effect below).
  const [pendingFirst, setPendingFirst] = useState<{ convId: string; text: string } | null>(null);

  const { data: conversations = [], isPending: convLoading } = useConversations();
  const { data: archivedConversations = [], isPending: archivedLoading } =
    useArchivedConversations(showArchived);
  const { data: agents = [] } = useChatAgents();
  const createConv = useCreateConversation();
  const renameConv = useRenameConversation();
  const deleteConv = useDeleteConversation();
  const archiveConv = useArchiveConversation();
  const unarchiveConv = useUnarchiveConversation();

  // Resolve the open conversation from the active list, the archived list,
  // or — when neither has it (archived deep-link, archived list not loaded) —
  // a by-id fetch. An archived or unknown id must never silently fall through
  // to the draft surface, where typing would create a NEW conversation.
  const listedConv =
    conversations.find((c) => c.id === routeId) ??
    archivedConversations.find((c) => c.id === routeId) ??
    null;
  const needsLookup = !!routeId && !convLoading && !listedConv;
  const lookup = useConversation(needsLookup && routeId ? routeId : "");
  const activeConv = listedConv ?? (needsLookup ? (lookup.data ?? null) : null);
  const activeLoading =
    !!routeId && !activeConv && (convLoading || (needsLookup && lookup.isPending));
  const activeNotFound = !!routeId && !activeConv && !activeLoading;
  const activeArchived = !!activeConv?.archived_at;
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

  // Chat talks only to Coffer-managed agents (claude_code / codex). The draft
  // defaults to the first available one; when none is available the draft
  // surface shows an install/configure empty state instead.
  const firstAvailableAgent = agents.find((a) => a.available)?.agent_key ?? null;
  const effectiveDraft = draftConfig ?? { agentKey: firstAvailableAgent ?? "" };

  const startDraft = () => {
    setDraftConfig({ agentKey: effectiveDraft.agentKey });
    navigate("/chat");
  };

  const selectConversation = (id: string) => {
    setDraftConfig(null);
    navigate(`/chat/${id}`);
  };

  const sendDraft = (text: string) => {
    // No per-turn working directory: send an empty agent_config and let the
    // backend default the cwd to the Coffer-managed workspace.
    createConv.mutate(
      {
        agent_key: effectiveDraft.agentKey,
        agent_config: {},
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

  const confirmArchive = () => {
    if (!archivingId) return;
    const id = archivingId;
    archiveConv.mutate(id, {
      onSuccess: () => {
        setArchivingId(null);
        if (routeId === id) navigate("/chat");
      },
    });
  };

  return {
    conversations,
    convLoading,
    agents,
    activeConv,
    // Route-id resolution state: still resolving / definitively unknown.
    activeLoading,
    activeNotFound,
    // True when the open conversation is archived (rendered read-only).
    activeArchived,
    activeAgent,
    turn,
    effectiveDraft,
    // True when no Coffer-managed agent (claude_code / codex) is available, so
    // the draft surface shows an install/configure empty state instead.
    noManagedAgent: !firstAvailableAgent,
    setDraftAgent: (agentKey: string) => setDraftConfig({ agentKey }),
    startDraft,
    selectConversation,
    sendDraft,
    creating: createConv.isPending,
    createError: createConv.isError ? createConv.error : null,
    resetCreateError: () => createConv.reset(),
    renameConversation: (id: string, title: string) => renameConv.mutate({ id, title }),
    deletingId,
    requestDelete: setDeletingId,
    confirmDelete,
    deletePending: deleteConv.isPending,
    // Archive / restore
    showArchived,
    toggleView: () => setShowArchived((v) => !v),
    listConversations: showArchived ? archivedConversations : conversations,
    listLoading: showArchived ? archivedLoading : convLoading,
    archivingId,
    requestArchive: setArchivingId,
    confirmArchive,
    archivePending: archiveConv.isPending,
    restoreConversation: (id: string) => unarchiveConv.mutate(id),
    restorePending: unarchiveConv.isPending,
  };
}
