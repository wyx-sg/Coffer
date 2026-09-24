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
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useChatTurn } from "@/lib/hooks/useChatTurn";

export function useChatController() {
  const navigate = useNavigate();
  const { id: routeId } = useParams<{ id?: string }>();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  // Draft top-bar selection (the agent + optional model + optional effort) before
  // the conversation exists; null until the user touches a selector — the
  // defaults are derived below. `model` is the agent's own per-conversation model
  // (agent_config.model, the coffer-model-is-an-internal-engine and
  // model-catalogue-read-from-the-agent ADRs); null inherits the active provider profile's
  // default. `effort` is the reasoning level that model runs at — its own field
  // beside the model, not part of its name — and it is carried here rather than
  // set after the fact because the FIRST turn is the one a user most wants to
  // pitch, and by the time the conversation exists that turn is already running.
  // There is no per-turn working-directory choice anymore: a turn runs in the
  // Coffer-managed workspace (~/.coffer/workspace) by default.
  const [draftConfig, setDraftConfig] = useState<{
    agentKey: string;
    model: string | null;
    effort: string | null;
  } | null>(null);
  // After creating from the draft, the first message is sent once the turn hook
  // re-binds to the new conversation id (see effect below).
  const [pendingFirst, setPendingFirst] = useState<{ convId: string; text: string } | null>(null);

  const { data: conversations = [], isPending: convLoading } = useConversations();
  const { data: archivedConversations = [], isPending: archivedLoading } =
    useArchivedConversations(showArchived);
  const { data: agents = [] } = useAgentProviders();
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
  const effectiveDraft = draftConfig ?? {
    agentKey: firstAvailableAgent ?? "",
    model: null,
    effort: null,
  };

  const startDraft = () => {
    setDraftConfig({ ...effectiveDraft });
    navigate("/chat");
  };

  const selectConversation = (id: string) => {
    setDraftConfig(null);
    navigate(`/chat/${id}`);
  };

  const sendDraft = (text: string) => {
    // No per-turn working directory: send an empty agent_config and let the
    // backend default the cwd to the Coffer-managed workspace. Carry the chosen
    // model and effort through only when set — unset inherits, respectively, the
    // global default and the agent's own level.
    const agent_config: Record<string, unknown> = {};
    if (effectiveDraft.model) agent_config.model = effectiveDraft.model;
    if (effectiveDraft.effort) agent_config.effort = effectiveDraft.effort;
    createConv.mutate(
      {
        agent_key: effectiveDraft.agentKey,
        agent_config,
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
    // Changing the agent clears any draft model AND effort override (different
    // agent → its own model namespace, its own default, and its own set of
    // levels — a level carried over could name something the new agent has
    // never heard of).
    setDraftAgent: (agentKey: string) => setDraftConfig({ agentKey, model: null, effort: null }),
    // Changing the model keeps the effort: the picker keeps a level it no longer
    // offers selectable rather than silently dropping it, so the trigger never
    // misreports what the first turn will run at.
    setDraftModel: (model: string | null) => setDraftConfig({ ...effectiveDraft, model }),
    setDraftEffort: (effort: string | null) => setDraftConfig({ ...effectiveDraft, effort }),
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
