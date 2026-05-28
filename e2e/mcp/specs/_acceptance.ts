// e2e/mcp/specs/_acceptance.ts
//
// Playwright mirror of e2e/web/specs/_acceptance.ts for the MCP cross-process
// e2e suite. scripts/audit_acceptance.py scans for the literal
// acceptance(spec, scenario, ...) call pattern in all files under e2e/, so
// every test registered here is automatically picked up by
// `make verify-acceptance`.

import { test } from "@playwright/test";

export function acceptance(
  spec: string,
  scenario: string,
  fn: Parameters<typeof test>[1],
): void {
  test(`[${spec}] ${scenario}`, fn);
}
