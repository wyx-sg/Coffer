// src/components/mcp/env/configTestBody.ts — the edit dialog's unsaved form as
// a `POST /resources/mcp_server/test-config` body.
//
// The same config the save would PATCH, with each Secret row resolved the way
// the save resolves it: a typed value travels in `secret_values` for this test
// only (nothing is written to the keychain), a cited stored secret stays a
// `secret_refs` entry — which the route refuses to release to an unsaved config.
import type { TFunction } from "i18next";

import type { McpConfigTestIn } from "@/lib/api/mcpTestConfig";
import { configTextFrom, type TransportForm } from "../editMcpServerSave";
import type { Timeouts } from "../serverTimeouts";
import { secretPlanOf } from "./rowsModel";

export function configTestBodyOf(
  name: string,
  config: unknown,
  form: TransportForm,
  timeouts: Timeouts,
  t: TFunction,
): McpConfigTestIn {
  const plan = secretPlanOf(form.rows, t);
  const parsed = JSON.parse(configTextFrom(config, form)) as { transport: Record<string, unknown> };
  const transport: Record<string, unknown> = { ...parsed.transport };
  delete transport.credential_refs;
  if (Object.keys(plan.cited).length > 0) transport.secret_refs = plan.cited;
  return {
    name,
    transport: transport as McpConfigTestIn["transport"],
    spawn_timeout_seconds: timeouts.spawn,
    request_timeout_seconds: timeouts.request,
    secret_values: Object.fromEntries(plan.typed.map((s) => [s.key, s.value])),
  };
}
