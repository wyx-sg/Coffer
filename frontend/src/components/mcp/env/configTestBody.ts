// src/components/mcp/env/configTestBody.ts — the edit dialog's unsaved form as
// a `POST /resources/mcp_server/test-config` body.
//
// The same config the save would PATCH, with each secret row resolved the way
// the save resolves it: a new secret's value travels in `secret_values` for this
// test only (nothing is written to Secrets), a stored secret stays a
// `secret_refs` entry — which the route refuses to release to an unsaved config.
import type { McpConfigTestIn } from "@/lib/api/mcpTestConfig";
import { configTextFrom, type TransportForm } from "@/lib/mcp/editMcpServerSave";
import type { Timeouts } from "@/lib/mcp/serverTimeouts";
import { keptRows, secretRefsForSave, secretRefsOf } from "@/lib/mcp/serverRows";

export function configTestBodyOf(
  name: string,
  config: unknown,
  form: TransportForm,
  timeouts: Timeouts,
): McpConfigTestIn {
  const parsed = JSON.parse(configTextFrom(config, form)) as { transport: Record<string, unknown> };
  const transport: Record<string, unknown> = { ...parsed.transport };
  delete transport.secret_refs;
  const stored = secretRefsForSave(
    form.rows.filter((r) => r.value.kind === "stored"),
    secretRefsOf(config),
  );
  if (Object.keys(stored).length > 0) transport.secret_refs = stored;
  const typed: Record<string, string> = {};
  for (const r of keptRows(form.rows)) {
    if (r.value.kind === "new") typed[r.key.trim()] = r.value.value;
  }
  return {
    name,
    transport: transport as McpConfigTestIn["transport"],
    spawn_timeout_seconds: timeouts.spawn,
    request_timeout_seconds: timeouts.request,
    secret_values: typed,
  };
}
