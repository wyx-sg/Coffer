// src/lib/hooks/useActivityLookups.ts — the agents and MCP servers Activity's filters list and its rows name.
//
// Read from each kind's own list (spec web-ui "Read each Activity tab from
// its record owner's route": the page adds no route of its own), and shaped
// once for the three places that need them: the filter pills, the rows'
// agent badges and the client-side predicate.
import { useMemo } from "react";

import { useAgents } from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";

/** @ui-only An agent as the who filter lists it and a row shows it. */
interface ActivityAgent {
  uid: string;
  type: string;
  name: string;
}

/** @ui-only An MCP server as the server filter lists it. */
export interface ActivityServer {
  uid: string;
  label: string;
}

export function useActivityLookups() {
  const agentsQuery = useAgents();
  const serversQuery = useResources("mcp_server");
  return useMemo(() => {
    const agents: ActivityAgent[] = (agentsQuery.data ?? []).map((a) => ({
      uid: a.uid,
      type: a.type,
      name: a.display_name,
    }));
    const servers = serversQuery.data ?? [];
    return {
      agents,
      agentLooks: new Map(agents.map((a) => [a.uid, { type: a.type, name: a.name }])),
      agentNames: new Map(agents.map((a) => [a.uid, a.name])),
      servers: servers.map((s): ActivityServer => ({ uid: s.uid, label: s.title || s.name })),
      serverNames: new Map(servers.map((s) => [s.uid, s.name])),
    };
  }, [agentsQuery.data, serversQuery.data]);
}
