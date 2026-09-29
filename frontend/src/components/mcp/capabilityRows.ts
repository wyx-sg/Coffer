// frontend/src/components/mcp/capabilityRows.ts — one server's tools /
// resources / prompts flattened into the row shape CapabilityList renders.
//
// Split out of CapabilityList.tsx to keep that file within its size budget.
import type { components } from "@/lib/api/types";
import { declaresParameters } from "./declaresParameters";

type ToolView = components["schemas"]["MCPToolView"];
type ResourceView = components["schemas"]["MCPResourceView"];
type PromptView = components["schemas"]["MCPPromptView"];
export type CapabilityKind = "tool" | "resource" | "prompt";

export interface CapabilityLists {
  kind: CapabilityKind;
  tools?: ToolView[];
  resources?: ResourceView[];
  prompts?: PromptView[];
}

export interface RowDescriptor {
  key: string;
  prefixed: string;
  description: string | null | undefined;
  enabled: boolean;
  schema?: Record<string, unknown>;
  /** Length of `mcp__coffer__<prefixed>` — the name a client shows. Tools and
   *  prompts only; a resource is addressed by URI, not by a tool name. */
  clientNameLength?: number;
}

/** The limit model provider APIs place on a tool name (spec mcp-gateway "Flag
 *  tools whose client-visible name is too long"). Flagging only: the tool stays
 *  enabled and listed under its usual name. */
export const CLIENT_NAME_LIMIT = 64;

export function toRows(props: CapabilityLists): RowDescriptor[] {
  if (props.kind === "tool" && props.tools) {
    return props.tools.map((t) => {
      const schema = t.input_schema as Record<string, unknown> | undefined;
      return {
        key: t.original_name,
        prefixed: t.prefixed_name,
        description: t.description,
        enabled: t.enabled,
        schema: declaresParameters(schema) ? schema : undefined,
        clientNameLength: t.client_name_length,
      };
    });
  }
  if (props.kind === "resource" && props.resources) {
    return props.resources.map((r) => ({
      key: r.original_uri,
      prefixed: r.prefixed_uri,
      description: r.description,
      enabled: r.enabled,
    }));
  }
  if (props.kind === "prompt" && props.prompts) {
    return props.prompts.map((p) => ({
      key: p.original_name,
      prefixed: p.prefixed_name,
      description: p.description,
      enabled: p.enabled,
      clientNameLength: p.client_name_length,
    }));
  }
  return [];
}
