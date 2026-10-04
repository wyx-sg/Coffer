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

const one = (uid: string, sessionId: string) => ({
  params: { path: { uid, session_id: sessionId } },
});

export const agentSessionsApi = {
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
