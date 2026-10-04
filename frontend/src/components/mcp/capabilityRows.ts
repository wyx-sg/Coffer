// frontend/src/components/mcp/capabilityRows.ts — what a capability row's switch needs, and the tool-name limit.

export type CapabilityKind = "tool" | "resource" | "prompt";

/** @ui-only The part of a tool, resource or prompt row its enable switch reads. */
export interface RowDescriptor {
  key: string;
  enabled: boolean;
}

/** The limit model provider APIs place on a tool name (spec mcp-gateway "Flag
 *  tools whose client-visible name is too long"). Flagging only: the tool stays
 *  enabled and listed under its usual name. */
export const CLIENT_NAME_LIMIT = 64;
