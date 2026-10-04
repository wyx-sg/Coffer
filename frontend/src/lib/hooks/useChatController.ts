// src/lib/hooks/useChatController.ts
// Orchestration for the Conversations page: binds the conversation/agent
// queries, the streaming turn, the URL filters and the draft → create →
// first-message flow, exposing a flat interface the page renders.
//
// Addresses: `/conversations` is the list, `/conversations/:id` an open
// conversation, `/conversations/new` the draft New conversation opens (spec chat
// "Create the conversation on the first send": the draft is not a row, its first
// send creates one). The list's filters ride along as search params. A
// hand-off (lib/conversations/handoff.ts) opens the draft with an agent, a
// folder and a prompt already in the composer; it is never sent for the person.
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import {
  useConversation,
  useCreateConversation,
  useRenameConversation,
  useDeleteConversation,
  useArchiveConversation,
  useUnarchiveConversation,
} from "@/lib/hooks/useConversations";
import { useConversationList } from "@/lib/hooks/useConversationList";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useChatTurn } from "@/lib/hooks/useChatTurn";
import { useConversationFilters } from "@/lib/hooks/useConversationFilters";
import { filterConversations } from "@/lib/conversations/filters";
import { readDraftAgentState, readHandoffState } from "@/lib/conversations/handoff";
import {
  defaultDraftAgent,
  readLastWorkingDir,
  rememberAgent,
  rememberWorkingDir,
} from "@/lib/conversations/draftMemory";
import type { ChatAttachment } from "@/lib/api/chat";
import type { ComposerRestore } from "@/lib/hooks/useComposerRestore";

/** The draft's route segment: `/conversations/new`. */
const DRAFT_ID = "new";

/** The draft's first message, bound for the conversation the draft created. */
interface FirstMessage {
  convId: string;
  text: string;
  attachments: ChatAttachment[];
}

/** What the draft will create: the agent, where it runs, and how. `model` and
 *  `effort` null inherit the agent's own defaults; `cwd` null is Coffer's own
 *  workspace (~/.coffer/content/workspace). */
/** @ui-only draft form state; never crosses the wire. */
export interface DraftConfig {
  agentKey: string;
  cwd: string | null;
  model: string | null;
  effort: string | null;
}

export function useChatController() {
  const navigate = useNavigate();
  const location = useLocation();
  const { id: routeParam } = useParams<{ id?: string }>();
  const isDraft = routeParam === DRAFT_ID;
  const routeId = isDraft ? undefined : routeParam;
  const { filters, setFilters, search } = useConversationFilters();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // The draft's choices, null until a selector (or a hand-off) sets them —
  // the defaults are derived below. They are carried into the create call rather
  // than set after the fact because the FIRST turn is the one a user most wants
  // to pitch, and by the time the conversation exists that turn is running.
  const [draftConfig, setDraftConfig] = useState<DraftConfig | null>(null);
  // After creating from the draft, the first message is sent once the turn hook
  // re-binds to the new conversation id (see effect below).
  const [pendingFirst, setPendingFirst] = useState<FirstMessage | null>(null);
  // A first message the daemon refused (e.g. ATTACHMENT_NOT_FOUND) once its
  // conversation existed: its text and chips go to the new conversation's composer.
  const [refusedFirst, setRefusedFirst] = useState<FirstMessage | null>(null);
  const clearRefusedFirst = useCallback(() => setRefusedFirst(null), []);
  // A hand-off's prompt, typed into the draft's composer once it mounts.
  const [draftPrefill, setDraftPrefill] = useState<ComposerRestore | null>(null);
  const clearDraftPrefill = useCallback(() => setDraftPrefill(null), []);
  // The draft was opened by a hand-off: the box says nothing is sent until Send.
  const [draftFromHandoff, setDraftFromHandoff] = useState(false);

  // Apply a hand-off once, then drop it from the history entry so a reload or
  // Back does not type the prompt again.
  const handoffState: unknown = isDraft ? location.state : null;
  const { pathname, search: locationSearch } = location;
  useEffect(() => {
    const handoff = readHandoffState(handoffState);
    const draftAgent = handoff ? null : readDraftAgentState(handoffState);
    if (handoff) {
      setDraftConfig({ agentKey: handoff.agentKey, cwd: handoff.cwd, model: null, effort: null });
      setDraftPrefill({ text: handoff.prompt, attachments: [] });
      setDraftFromHandoff(true);
    } else if (draftAgent) {
      // An agent page's New conversation: a fresh draft on that agent, nothing typed.
      setDraftConfig({
        agentKey: draftAgent,
        cwd: readLastWorkingDir(),
        model: null,
        effort: null,
      });
      setDraftPrefill(null);
      setDraftFromHandoff(false);
    } else {
      return;
    }
    navigate(`${pathname}${locationSearch}`, { replace: true, state: null });
  }, [handoffState, pathname, locationSearch, navigate]);

  // The title search is the server's: typed text waits for a pause, then the
  // list starts again from its first page for it.
  // Its text lives in the URL (`?q=`), so a search is a link.
  const titleSearch = filters.q;
  const setTitleSearch = useCallback(
    (text: string) => setFilters({ ...filters, q: text }),
    [filters, setFilters],
  );
  const q = useDebouncedValue(titleSearch.trim());
  const active = useConversationList({ archived: false, q });
  const archivedList = useConversationList({ archived: true, q, enabled: filters.archived });
  const conversations = active.items;
  const archivedConversations = archivedList.items;
  const convLoading = active.isLoading;
  const { data: agents = [] } = useAgentProviders();
  const createConv = useCreateConversation();
  const renameConv = useRenameConversation();
  const deleteConv = useDeleteConversation();
  const archiveConv = useArchiveConversation();
  const unarchiveConv = useUnarchiveConversation();

  // Resolve the open conversation from the active list, the archived list, or —
  // when neither has it — a by-id fetch. An archived or unknown id must never
  // silently fall through to the draft surface.
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
  const activeAgent = activeConv
    ? agents.find((a) => a.agent_key === activeConv.agent_key)
    : undefined;

  const turn = useChatTurn(activeConv?.id ?? "");

  // Fire the draft's first message once the turn hook is bound to the new
  // conversation. Keyed on the stable `send`: a render that lands before
  // `setPendingFirst(null)` is processed must not send it a second time.
  const sendTurn = turn.send;
  useEffect(() => {
    if (pendingFirst && activeConv?.id === pendingFirst.convId) {
      const first = pendingFirst;
      setPendingFirst(null);
      void sendTurn(first.text, first.attachments).then((accepted) => {
        if (!accepted) setRefusedFirst(first);
      });
    }
  }, [pendingFirst, activeConv?.id, sendTurn]);

  // Conversations run only on Coffer-managed agents (claude_code / codex); with
  // none available the draft shows how to get one instead of a composer.
  const firstAvailableAgent = agents.find((a) => a.available)?.agent_key ?? null;
  // The defaults are the agent and folder the last conversation used (the first
  // agent that can run, Coffer's workspace, when there is none to remember).
  const effectiveDraft: DraftConfig = draftConfig ?? {
    agentKey: defaultDraftAgent(agents),
    cwd: readLastWorkingDir(),
    model: null,
    effort: null,
  };

  const listPath = `/conversations${search}`;
  const pathFor = (id: string) => `/conversations/${encodeURIComponent(id)}${search}`;

  /** New conversation: straight to the draft, on the remembered defaults; what is
   *  chosen (agent, folder, model, effort) is chosen on the draft itself. */
  const openDraft = () => {
    setDraftConfig(null);
    setDraftPrefill(null);
    setDraftFromHandoff(false);
    navigate(pathFor(DRAFT_ID));
  };

  const selectConversation = (id: string) => navigate(pathFor(id));

  // Resolves whether the conversation was created; a failed create keeps the
  // draft composer's chips (the error shows as `createError`).
  const sendDraft = (text: string, attachments: ChatAttachment[] = []) =>
    new Promise<boolean>((resolve) => {
      // Only what was chosen is sent: unset inherits the agent's own model and
      // level, and no cwd runs the turn in Coffer's workspace.
      const agent_config: Record<string, unknown> = {};
      if (effectiveDraft.cwd) agent_config.cwd = effectiveDraft.cwd;
      if (effectiveDraft.model) agent_config.model = effectiveDraft.model;
      if (effectiveDraft.effort) agent_config.effort = effectiveDraft.effort;
      createConv.mutate(
        { agent_key: effectiveDraft.agentKey, agent_config },
        {
          onSuccess: (created) => {
            rememberWorkingDir(effectiveDraft.cwd);
            rememberAgent(effectiveDraft.agentKey);
            setPendingFirst({ convId: created.id, text, attachments });
            setDraftConfig(null);
            setDraftFromHandoff(false);
            navigate(pathFor(created.id));
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
        if (routeId === id) navigate(listPath);
      },
    });
  };

  // Archive asks nothing first: it loses nothing, and Unarchive brings it back.
  const archiveConversation = (id: string) => {
    archiveConv.mutate(id, {
      onSuccess: () => {
        if (routeId === id) navigate(listPath);
      },
    });
  };

  const view = filters.archived ? archivedList : active;
  const listed = view.items;

  return {
    agents,
    filters,
    setFilters,
    listPath,
    pathFor,
    /** Every conversation of the current view, before the filters. */
    allConversations: listed,
    /** The current view (active or archived) narrowed by the URL filters. */
    listConversations: filterConversations(listed, filters),
    listLoading: view.isLoading,
    /** More conversations exist past the loaded pages (the filters are applied to what is loaded). */
    hasMore: view.hasMore,
    loadMore: view.loadMore,
    /** The server's count of the current view (archived and search applied). */
    total: view.total,
    /** The list's first page failed to load. */
    listError: view.error,
    refetchList: view.refetch,
    isLoadingMore: view.isLoadingMore,
    /** The title search box's text, and the settled text the server was asked for. */
    titleSearch,
    setTitleSearch,
    searching: q !== "",
    isDraft,
    routeId,
    activeConv,
    activeLoading,
    activeNotFound,
    /** The open conversation is archived: read-only until unarchived. */
    activeArchived: !!activeConv?.archived_at,
    activeAgent,
    turn,
    effectiveDraft,
    noManagedAgent: !firstAvailableAgent,
    // A different agent has its own models and levels: the draft's model and
    // effort are cleared rather than carried over.
    setDraftAgent: (agentKey: string) =>
      setDraftConfig({ ...effectiveDraft, agentKey, model: null, effort: null }),
    setDraftCwd: (cwd: string | null) => setDraftConfig({ ...effectiveDraft, cwd }),
    setDraftModel: (model: string | null) => setDraftConfig({ ...effectiveDraft, model }),
    setDraftEffort: (effort: string | null) => setDraftConfig({ ...effectiveDraft, effort }),
    openDraft,
    selectConversation,
    sendDraft,
    refusedFirst: refusedFirst?.convId === activeConv?.id ? refusedFirst : null,
    clearRefusedFirst,
    /** A hand-off's prompt for the draft's composer; nothing sends it. */
    draftPrefill,
    draftFromHandoff,
    clearDraftPrefill,
    creating: createConv.isPending,
    createError: createConv.isError ? createConv.error : null,
    resetCreateError: () => createConv.reset(),
    renameConversation: (id: string, title: string) => renameConv.mutate({ id, title }),
    deletingId,
    /** The conversation the delete confirmation names, when it is loaded. */
    deletingConversation: deletingId
      ? ([...conversations, ...archivedConversations, activeConv].find(
          (c) => c?.id === deletingId,
        ) ?? null)
      : null,
    requestDelete: setDeletingId,
    confirmDelete,
    deletePending: deleteConv.isPending,
    archiveConversation,
    unarchiveConversation: (id: string) => unarchiveConv.mutate(id),
    unarchivePending: unarchiveConv.isPending,
  };
}

export type ChatController = ReturnType<typeof useChatController>;
