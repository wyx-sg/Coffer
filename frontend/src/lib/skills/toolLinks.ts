// frontend/src/lib/skills/toolLinks.ts — where a tool a skill calls lives.
import type { SkillToolState } from "@/lib/skills/attention";

/** The page of an MCP server, or of a custom-tool group, by its fixed name. */
export function toolHref(tool: Pick<SkillToolState, "kind" | "name">): string {
  const base = tool.kind === "mcp_server" ? "/mcp-servers" : "/custom-tools";
  return `${base}/${encodeURIComponent(tool.name)}`;
}
