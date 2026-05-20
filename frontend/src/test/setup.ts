import "@testing-library/jest-dom";
import { test } from "vitest";
import type { TestAPI } from "vitest";

// Attach a `test.acceptance(spec, scenario, fn)` helper that tags a Vitest
// test with a Coffer spec acceptance marker, matching the Python convention
// in backend/pyproject.toml `[tool.pytest.ini_options].markers`.
//
// `scripts/audit_acceptance.py` regex-detects calls of this shape and
// cross-references them against `specs/<id>/spec.md` `## Acceptance
// Scenarios`. See agents/testing.md.
//
// Usage:
//   test.acceptance("001-mcp-servers", "register and list", async () => {
//     // ...
//   });
//
// The wired-up smoke test in `src/test/acceptance.test.ts` ensures the
// helper actually exists at runtime; if vitest's exported `test` ever
// changes in a way that breaks this assignment, that test fails loudly.

declare module "vitest" {
  interface TestAPI {
    acceptance: (
      spec: string,
      scenario: string,
      fn: () => void | Promise<void>,
    ) => void;
  }
}

(test as TestAPI).acceptance = (
  spec: string,
  scenario: string,
  fn: () => void | Promise<void>,
): void => {
  test(`[${spec}] ${scenario}`, fn);
};
