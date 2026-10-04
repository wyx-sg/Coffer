// src/lib/customTools/reimport.ts — what a re-import's preview lists, as one row per change: operations to
// add (reads start ticked, writes do not), tools the spec changed, tools it dropped.
import type { CustomToolGroup, ReimportPreview } from "@/lib/api/customTools";
import type { ChangeOp } from "@/lib/changePreview/changeCounts";
import { operationChangesData } from "@/lib/customTools/operations";

type Added = ReimportPreview["added"][number];

export interface ReimportItem {
  /** Unique across the list: `add:<key>`, `modify:<tool>`, `remove:<tool>`. */
  id: string;
  op: ChangeOp;
  /** The tool's name. */
  name: string;
  /** "GET /payouts"; empty when the group no longer has the tool's request. */
  request: string;
  /** Add: the operation key to send back when ticked. */
  key?: string;
  /** Add: the operation changes data, so it starts unticked. */
  write?: boolean;
  /** Modify: arguments the new spec requires that the tool did not. */
  newRequired?: string[];
  /** Add: the operation's text in the spec. */
  source?: Added["source"];
  /** Modify: the operation's text before and after, and where the new one starts. */
  oldText?: string | null;
  newText?: string | null;
  newStart?: number | null;
}

export function reimportItems(p: ReimportPreview, group: CustomToolGroup): ReimportItem[] {
  const tools = new Map(group.tools.map((tool) => [tool.name, tool]));
  return [
    ...p.added.map(
      (op): ReimportItem => ({
        id: `add:${op.key}`,
        op: "add",
        name: op.tool.name,
        request: `${op.tool.method ?? "GET"} ${op.tool.path}`,
        key: op.key,
        write: operationChangesData(op),
        source: op.source,
      }),
    ),
    ...p.changed.map(
      (c): ReimportItem => ({
        id: `modify:${c.name}`,
        op: "modify",
        name: c.name,
        request: `${c.method} ${c.path}`,
        newRequired: c.new_required,
        oldText: c.old_text,
        newText: c.new_text,
        newStart: c.new_start_line,
      }),
    ),
    ...p.removed.map((name): ReimportItem => {
      const tool = tools.get(name);
      return {
        id: `remove:${name}`,
        op: "remove",
        name,
        request: tool ? `${tool.method} ${tool.path}` : "",
      };
    }),
  ];
}

/** The operation keys ticked by default: the reads. */
export function defaultAdds(items: readonly ReimportItem[]): string[] {
  return items.filter((i) => i.op === "add" && !i.write).map((i) => i.key as string);
}
