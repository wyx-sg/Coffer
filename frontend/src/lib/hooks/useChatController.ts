// src/lib/hooks/useChatController.ts
// Orchestration for the Chat page: binds the conversation/agent queries, the
// streaming turn, and the draft → create → first-message flow, exposing a flat
// interface the ChatPage component renders. Keeping this out of the page keeps
// the component presentational (and under the file-size limit).
import { useCallback, useEffect, useState } from "react";
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
import type { ChatAttachment } from "@/lib/api/chat";

/** The draft's first message, bound for the conversation the draft created. */
interface FirstMessage {
  convId: string;
  text: string;
  attachments: ChatAttachment[];
}

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
  const [pendingFirst, setPendingFirst] = useState<FirstMessage | null>(null);
  // A first message the daemon refused (e.g. ATTACHMENT_NOT_FOUND) once its
  // conversation existed: the draft's composer is gone by then, so its text and
  // chips are handed to the new conversation's composer rather than lost.
  const [refusedFirst, setRefusedFirst] = useState<FirstMessage | null>(null);
  const clearRefusedFirst = useCallback(() => setRefusedFirst(null), []);

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
  // wrong thread. Keyed on the stable `send`, not the `turn` object (new every
  // render): a render that lands before `setPendingFirst(null)` is processed
  // must not send the message a second time.
  const sendTurn = turn.send;
  useEffect(() => {
    if (pendingFirst && activeConv?.id === pendingFirst.convId) {
      const first = pendingFirst;
      setPendingFirst(null);
      // A refusal is also the turn's `error`, shown in the thread's banner.
      void sendTurn(first.text, first.attachments).then((accepted) => {
        if (!accepted) setRefusedFirst(first);
      });
    }
  }, [pendingFirst, activeConv?.id, sendTurn]);

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

  // Resolves whether the conversation was created; a failed create keeps the
  // draft composer's chips (the error shows as `createError`). A first message
  // refused after the create comes back as `refusedFirst`.
  const sendDraft = (text: string, attachments: ChatAttachment[] = []) =>
    new Promise<boolean>((resolve) => {
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
            setPendingFirst({ convId: created.id, text, attachments });
            setDraftConfig(null);
            navigate(`/chat/${created.id}`);
            resolve(true);
          },
          onError: () => resolve(false),
        },
      );
    });

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
    // The refused first message, for the open conversation's composer to take back.
    refusedFirst: refusedFirst?.convId === activeConv?.id ? refusedFirst : null,
    clearRefusedFirst,
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
