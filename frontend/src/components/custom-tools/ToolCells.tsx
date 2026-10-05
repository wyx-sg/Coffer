// src/components/custom-tools/ToolCells.tsx — cells of a group's Tools table: a 24-hour count, a tool's exposure control.
import { McpToolExposure } from "@/components/mcp/server/McpToolExposure";
import type { ToolRow } from "@/components/mcp/server/toolRows";
import { cn } from "@/lib/utils";

/** A 24-hour count; a tool with no call in 24 hours reads "—" in both columns. */
export function Count({
  value,
  none,
  danger = false,
}: {
  value: number;
  none: boolean;
  danger?: boolean;
}) {
  return (
    <span className={cn("text-xs tabular-nums", danger && value > 0 ? "text-danger" : "text-text")}>
      {none ? "—" : value}
    </span>
  );
}

/** A tool's exposure control; a tool that is off, or one tiering has not reported, reads "—". */
export function ExposureCell({
  serverUid,
  tool,
  exposure,
}: {
  serverUid: string;
  tool: string;
  exposure: ToolRow["exposure"] | undefined;
}) {
  if (!exposure) return <span className="text-xs text-text-subtle">—</span>;
  return <McpToolExposure serverUid={serverUid} tool={tool} exposure={exposure} />;
}
