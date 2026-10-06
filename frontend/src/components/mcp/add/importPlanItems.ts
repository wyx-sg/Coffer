// frontend/src/components/mcp/add/importPlanItems.ts — one direct MCP entry as
// the daemon's import plan names it (`POST /agents/mcp-import/plan`, spec
// agent-registry "Plan an import of agents' direct MCP entries"). The MCP
// servers page's first-run card plans the agents' entries only to show the
// file each one sits in; importing happens on the agent's MCP servers tab.
import type { McpImportEntryIn } from "@/lib/api/mcpImport";
import type { McpEntryOut } from "@/lib/api/agents-workspace";

export function toEntryIn(agentUid: string, entry: McpEntryOut): McpImportEntryIn {
  return { agent_uid: agentUid, name: entry.name, source: entry.source };
}
