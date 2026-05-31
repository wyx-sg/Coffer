// frontend/src/lib/hooks/useChatTargets.ts — the set of agents a new
// conversation can target (spec 008-builtin-agent-chat). Two sources are merged
// into one flat picker list:
//   • built-in agent(s)  → resources of kind `builtin_agent`  (ref `builtin_agent:<name>`)
//   • managed agents      → /agents                            (ref `agent:<name>`)
import { useQuery } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

export type ChatTargetKind = "builtin_agent" | "agent";

export interface ChatTarget {
  /** `<kind>:<name>` — the `target_ref` POSTed to create a conversation. */
  ref: string;
  kind: ChatTargetKind;
  name: string;
  /** Free-text description shown under the name, when the source provides one. */
  description: string | null;
}

export function useChatTargets() {
  return useQuery({
    queryKey: ["chat", "targets"],
    queryFn: async (): Promise<ChatTarget[]> => {
      const client = getApiClient();
      const [builtinRes, agentsRes] = await Promise.all([
        client.GET("/resources", { params: { query: { kind: "builtin_agent" } } }),
        agentsApi.list(),
      ]);
      if (builtinRes.error)
        throwApiError(builtinRes.error, "INTERNAL_ERROR", "failed to list built-in agents");

      const builtin: ChatTarget[] = (builtinRes.data?.resources ?? []).map((r) => ({
        ref: r.ref,
        kind: "builtin_agent",
        name: r.name,
        description: r.description ?? null,
      }));
      const external: ChatTarget[] = agentsRes.items.map((a) => ({
        ref: `agent:${a.name}`,
        kind: "agent",
        name: a.name,
        description: a.description ?? null,
      }));
      // Built-in agent(s) first — they are the recommended default target.
      return [...builtin, ...external];
    },
  });
}
