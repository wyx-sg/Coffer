// src/lib/agents/agentFilter.ts — the `?agent=<uid>` filter of the global Skills and MCP servers pages.
//
// An agent's Skills / MCP servers tab links to `/skills?agent=<uid>` and
// `/mcp-servers?agent=<uid>`: the page then lists only what reaches that agent
// and shows a removable "Agent: <name>" pill in its filter row.
import { useCallback, useMemo } from "react";

import { agentTypeLabel } from "@/lib/agents/display";
import { reachesAgent } from "@/lib/agents/counts";
import { useAgents } from "@/lib/hooks/useAgents";
import { useSearchParamsKeepingState } from "@/lib/hooks/useSearchParamsKeepingState";
import type { Scope } from "@/lib/hooks/useScope";

const PARAM = "agent";

export interface AgentFilter {
  uid: string;
  /** The agent's product name; null until the agents are read (or when the uid matches none). */
  label: string | null;
  clear: () => void;
  /** Whether a row with these reach fields reaches the filtered agent. */
  matches: (row: { enabled: boolean; scope: Scope | null | undefined }) => boolean;
}

/** Point `?agent=` at an agent, or drop it (null) — what the Skills page's reach filter writes. */
export function useSetAgentFilter(): (uid: string | null) => void {
  const [, setParams] = useSearchParamsKeepingState();
  return useCallback(
    (uid) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (uid) next.set(PARAM, uid);
          else next.delete(PARAM);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
}

/** The page's agent filter, or null when `?agent=` is absent. */
export function useAgentFilter(): AgentFilter | null {
  const [params, setParams] = useSearchParamsKeepingState();
  const { data: agents } = useAgents();
  const uid = params.get(PARAM);
  const type = agents?.find((a) => a.uid === uid)?.type;
  // Stable while the address and the agents are, so a list can depend on it.
  return useMemo(() => {
    if (!uid) return null;
    return {
      uid,
      label: type ? agentTypeLabel(type) : null,
      clear: () =>
        setParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.delete(PARAM);
            return next;
          },
          { replace: true },
        ),
      matches: (row) => reachesAgent(uid, { enabled: row.enabled, scope: row.scope ?? null }),
    };
  }, [uid, type, setParams]);
}
