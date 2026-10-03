// src/lib/customTools/drafts.ts — what a tool form starts from.
import type { CustomTool, CustomToolIn } from "@/lib/api/customTools";

/** A group name: lowercase, digits and `-`, up to 24 characters. */
const GROUP_NAME_RE = /^[a-z0-9][a-z0-9-]{0,23}$/;

export function isGroupName(name: string): boolean {
  return GROUP_NAME_RE.test(name);
}

/** A saved tool as the draft its editor starts from. */
export function draftOf(tool: CustomTool): CustomToolIn {
  return {
    name: tool.name,
    description: tool.description,
    method: tool.method,
    path: tool.path,
    headers: { ...tool.headers },
    body_template: tool.body_template,
    input_schema: tool.input_schema,
    enabled: tool.enabled,
    changes_data: tool.changes_data,
    operation: tool.operation,
  };
}

export function emptyDraft(): CustomToolIn {
  return {
    name: "",
    description: "",
    method: "GET",
    path: "/",
    headers: {},
    body_template: null,
    input_schema: { type: "object", properties: {} },
    enabled: true,
    changes_data: false,
  };
}
