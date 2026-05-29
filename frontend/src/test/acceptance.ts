import { test } from "vitest";

// Acceptance-scenario helper for Vitest tests. Mirrors the Python
// pytest.mark.acceptance marker registered in backend/pyproject.toml.
//
// scripts/audit_acceptance.py strips JS/TS comments and then regex-detects
// real acceptance(...) calls, cross-referencing them against
// specs/<id>/spec.md '## Acceptance Scenarios'. See agents/testing.md for
// the full convention.
//
// Real usage lives in e2e/mcp/specs and frontend/**/*.test.ts(x).
// Intentionally no inline code-example here: the audit script ignores
// commented code, but keeping examples verbatim out of this file removes
// any chance of a future regex change re-introducing the trap.
//
// (Previously implemented as test.acceptance via declaration merging onto
// Vitest's TestAPI; switched to a standalone export because merging into
// TestAPI is fragile.)

export function acceptance(spec: string, scenario: string, fn: () => void | Promise<void>): void {
  test(`[${spec}] ${scenario}`, fn);
}
