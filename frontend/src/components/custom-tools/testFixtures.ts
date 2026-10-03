// src/components/custom-tools/testFixtures.ts — groups and tools the Custom tools tests render.
import type { CustomTool, CustomToolGroup } from "@/lib/api/customTools";

export function makeTool(overrides: Partial<CustomTool> = {}): CustomTool {
  const name = overrides.name ?? "get_invoice";
  return {
    name,
    agent_name: `billing__${name}`,
    description: "Read one invoice",
    method: "GET",
    path: "/invoices/{id}",
    headers: {},
    body_template: null,
    input_schema: {
      type: "object",
      properties: { id: { type: "string", description: "Invoice id" } },
      required: ["id"],
    },
    enabled: true,
    changes_data: false,
    changes_data_set: false,
    operation: null,
    reach_override: null,
    calls_24h: 0,
    failures_24h: 0,
    ...overrides,
  };
}

export function makeGroup(overrides: Partial<CustomToolGroup> = {}): CustomToolGroup {
  const name = overrides.name ?? "billing";
  return {
    uid: `uid-${name}`,
    name,
    description: null,
    enabled: true,
    base_url: `https://${name}.internal.example/v2`,
    headers: [
      { name: "Authorization", value: null, secret: `${name}-token`, secret_state: "present" },
    ],
    timeout_seconds: 30,
    scope: null,
    source: null,
    health: "healthy",
    health_reason: null,
    secret_state: "present",
    pending_approvals: [],
    pending_secrets: [],
    calls_24h: 58,
    failures_24h: 2,
    last_call_at: null,
    tools: [makeTool()],
    created_at: "2026-09-20T09:40:00Z",
    updated_at: "2026-09-20T09:40:00Z",
    ...overrides,
  };
}
