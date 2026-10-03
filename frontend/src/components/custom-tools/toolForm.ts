// src/components/custom-tools/toolForm.ts — what the tool drawer edits, and the request it sends.
import type { CustomTool, CustomToolIn, HttpMethod } from "@/lib/api/customTools";
import { draftOf, emptyDraft } from "@/lib/customTools/drafts";
import { changesDataByDefault } from "@/lib/customTools/groups";
import { argsFromSchema, schemaFromArgs, type ArgRow } from "@/lib/customTools/schemaArgs";

/** One header of this request, as a key/value row. */
export interface HeaderRow {
  key: string;
  value: string;
}

export interface ToolForm {
  name: string;
  description: string;
  method: HttpMethod;
  path: string;
  headers: HeaderRow[];
  body: string;
  args: ArgRow[];
  /** The schema the rows were read from; every key they do not edit survives. */
  schema: Record<string, unknown>;
  enabled: boolean;
  changesData: boolean;
  /** Set by hand rather than following the method. */
  changesDataSet: boolean;
}

export function formOf(tool: CustomTool | null): ToolForm {
  const draft = tool ? draftOf(tool) : emptyDraft();
  const method = draft.method ?? "GET";
  return {
    name: draft.name,
    description: draft.description ?? "",
    method,
    path: draft.path,
    headers: Object.entries(draft.headers ?? {}).map(([key, value]) => ({ key, value })),
    body: draft.body_template ?? "",
    args: argsFromSchema(draft.input_schema ?? {}),
    schema: draft.input_schema ?? { type: "object", properties: {} },
    enabled: draft.enabled ?? true,
    changesData: tool ? tool.changes_data : changesDataByDefault(method),
    changesDataSet: tool ? tool.changes_data_set : false,
  };
}

/** A method change moves the flag along while it follows the method. */
export function withMethod(form: ToolForm, method: HttpMethod): ToolForm {
  return {
    ...form,
    method,
    changesData: form.changesDataSet ? form.changesData : changesDataByDefault(method),
  };
}

/** The tool the form describes, as a create, a test run or an import sends it. */
export function toolOf(form: ToolForm): CustomToolIn {
  const headers = Object.fromEntries(
    form.headers.filter((h) => h.key.trim()).map((h) => [h.key.trim(), h.value]),
  );
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    method: form.method,
    path: form.path.trim(),
    headers,
    body_template: form.body.trim() ? form.body : null,
    input_schema: schemaFromArgs(form.args, form.schema),
    enabled: form.enabled,
    changes_data: form.changesDataSet ? form.changesData : null,
  };
}

/** What still blocks a save: the required fields. */
export function formReady(form: ToolForm): boolean {
  return form.name.trim() !== "" && form.path.trim() !== "" && form.description.trim() !== "";
}
