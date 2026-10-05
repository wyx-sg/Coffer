// frontend/src/lib/api/agentSessions.ts — request helpers for
// /api/v1/agents/{uid}/sessions: an agent's own sessions, listed, renamed and
// deleted through the agent (spec agent-registry "List an agent's native
// sessions through the agent", "Rename and delete a native session through the
// agent"). Wire types are the agent-registry contract's generated schemas;
// transport is the typed client (.agents/frontend.md §4).

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/agent-registry";

type Schemas = components["schemas"];

/** One session as the Sessions tab lists it. */
export type AgentSession = Schemas["AgentSessionOut"];

/** One page of sessions; `total` is null when the agent cannot count them (Codex). */
export type AgentSessionList = Schemas["AgentSessionListResponse"];

/** One row of the cross-agent list: the session plus whose it is; `session_id` is null for a channel conversation no turn has run on. */
export type AgentSessionRow = Schemas["AgentSessionRowOut"];

/** One page of every agent's sessions, with the agents that could not be read. */
export type AllAgentSessionsPage = Schemas["AllAgentSessionsResponse"];

const one = (uid: string, sessionId: string) => ({
  params: { path: { uid, session_id: sessionId } },
});

export const agentSessionsApi = {
  // Every managed agent's sessions in one list (spec agent-registry "List every
  // agent's sessions in one list"): `source` is `local` and channel uids, `agent`
  // agent keys; a cursor belongs to the filters it was issued for.
  listAll: (
    opts: {
      limit: number;
      cursor?: string | null;
      q?: string;
      source?: readonly string[];
      agent?: readonly string[];
    },
    signal?: AbortSignal,
  ): Promise<AllAgentSessionsPage> =>
    unwrap(
      getApiClient().GET("/agent-sessions", {
        signal,
        params: {
          query: {
            limit: opts.limit,
            ...(opts.cursor ? { cursor: opts.cursor } : {}),
            ...(opts.q ? { q: opts.q } : {}),
            ...(opts.source?.length ? { source: opts.source.join(",") } : {}),
            ...(opts.agent?.length ? { agent: opts.agent.join(",") } : {}),
          },
        },
      }),
    ),

  list: (
    uid: string,
    opts: { limit: number; cursor?: string | null; q?: string },
    signal?: AbortSignal,
  ): Promise<AgentSessionList> =>
    unwrap(
      getApiClient().GET("/agents/{uid}/sessions", {
        signal,
        params: {
          path: { uid },
          query: {
            limit: opts.limit,
            ...(opts.cursor ? { cursor: opts.cursor } : {}),
            ...(opts.q ? { q: opts.q } : {}),
          },
        },
      }),
    ),

  rename: (uid: string, sessionId: string, title: string): Promise<void> =>
    unwrapVoid(
      getApiClient().PATCH("/agents/{uid}/sessions/{session_id}", {
        ...one(uid, sessionId),
        body: { title },
      }),
    ),

  remove: (uid: string, sessionId: string): Promise<void> =>
    unwrapVoid(getApiClient().DELETE("/agents/{uid}/sessions/{session_id}", one(uid, sessionId))),
};
