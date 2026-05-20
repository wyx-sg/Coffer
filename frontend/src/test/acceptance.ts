import { test } from "vitest";

// Acceptance-scenario helper for Vitest tests. Mirrors the Python
// `@pytest.mark.acceptance(spec=..., scenario=...)` marker registered in
// backend/pyproject.toml.
//
// `scripts/audit_acceptance.py` regex-detects calls of this shape and
// cross-references them against `specs/<id>/spec.md` `## Acceptance
// Scenarios`. See agents/testing.md.
//
// Usage:
//   import { acceptance } from "@/test/acceptance";
//   acceptance("001-mcp-servers", "register and list", async () => { ... });
//
// (Previously implemented as `test.acceptance(...)` via declaration
// merging onto Vitest's TestAPI; switched to a standalone export because
// merging into TestAPI is fragile — see desktop/Cargo.lock-era PR.)

export function acceptance(
  spec: string,
  scenario: string,
  fn: () => void | Promise<void>,
): void {
  test(`[${spec}] ${scenario}`, fn);
}
