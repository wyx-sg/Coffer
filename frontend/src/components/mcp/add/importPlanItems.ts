// frontend/src/components/mcp/add/importPlanItems.ts — an import plan as change-preview items (board 4.1.18).
//
// The daemon plans the import (`POST /agents/mcp-import/plan`, spec
// agent-registry "Plan an import of agents' direct MCP entries"): the servers
// Coffer adds and, per agent config file, the redacted hunks it will write.
// This turns that plan into what the shared change preview shows — one
// "Coffer · N servers" item, then one item per file with its diff — and the
// "What will happen" sentences. Pure: no React; words come from `t`.
import type {
  ChangeItem,
  ChangeSummaryLine,
  DiffLine,
} from "@/components/change-preview/changeCounts";
import type { McpImportEntryIn, McpImportFile, McpImportPlan } from "@/lib/api/mcpImport";
import type { McpEntryOut } from "@/lib/api/agents";

/** The agent type the change preview groups Coffer's own item under. */
const COFFER_TARGET = "coffer";

type T = (key: string, options?: Record<string, unknown>) => string;

/** The address of one direct entry, the same in the plan request and in the checklist. */
export function entryKey(e: { agent_uid: string; name: string; source?: string | null }): string {
  return `${e.agent_uid}:${e.source ?? ""}:${e.name}`;
}

export function toEntryIn(agentUid: string, entry: McpEntryOut): McpImportEntryIn {
  return { agent_uid: agentUid, name: entry.name, source: entry.source };
}

function fileDiff(file: McpImportFile): DiffLine[] {
  const out: DiffLine[] = [];
  for (const hunk of file.hunks) {
    out.push({ kind: "hunk", text: hunk.header });
    for (const line of hunk.lines) {
      out.push({
        kind: line.kind,
        text: line.text,
        oldNo: line.old_line ?? undefined,
        newNo: line.new_line ?? undefined,
      });
    }
  }
  return out;
}

const listOf = (names: string[]) => names.join(", ");

export function planItems(plan: McpImportPlan, t: T): ChangeItem[] {
  const adds = plan.servers.filter((s) => s.op === "add");
  const items: ChangeItem[] = [];
  if (adds.length > 0) {
    items.push({
      id: "coffer",
      agentType: COFFER_TARGET,
      agentName: t("mcp.import.coffer"),
      path: t("mcp.import.serversItem", { count: adds.length }),
      op: "add",
    });
  }
  for (const file of plan.files) {
    items.push({
      id: `${file.agent_uid}:${file.path}`,
      agentType: file.agent_type,
      agentName: plan.agents.find((a) => a.uid === file.agent_uid)?.display_name,
      path: file.display_path,
      op: file.op,
      added: file.added_lines || undefined,
      removed: file.removed_lines || undefined,
      diff: fileDiff(file),
    });
  }
  return items;
}

export function planSummaries(plan: McpImportPlan, t: T): ChangeSummaryLine[] {
  const lines: ChangeSummaryLine[] = [];
  const adds = plan.servers.filter((s) => s.op === "add").map((s) => s.name);
  if (adds.length > 0) {
    lines.push({
      agentType: COFFER_TARGET,
      agentName: t("mcp.import.coffer"),
      text: t("mcp.import.happensCoffer", { names: listOf(adds), count: adds.length }),
    });
  }
  for (const agent of plan.agents) {
    if (agent.entries_removed.length === 0) continue;
    lines.push({
      agentType: agent.type,
      agentName: agent.display_name,
      text: t("mcp.import.happensAgent", {
        names: listOf(agent.entries_removed),
        count: agent.entries_removed.length,
      }),
    });
  }
  return lines;
}

/** How many servers the import brings into Coffer (the confirm button's number). */
export function addedCount(plan: McpImportPlan | undefined): number {
  return plan?.servers.filter((s) => s.op === "add").length ?? 0;
}
