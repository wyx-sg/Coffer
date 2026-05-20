import "@testing-library/jest-dom";
import { test } from "vitest";

// Attach a `test.acceptance(spec, scenario, fn)` helper that tags the test
// with a Coffer spec acceptance marker, matching the Python convention in
// backend/pyproject.toml `[tool.pytest.ini_options].markers`.
//
// `scripts/audit_acceptance.py` cross-references these calls against
// `specs/<id>/spec.md` `## Acceptance Scenarios` section.
//
// Usage:
//   test.acceptance("001-mcp-servers", "register and list", async () => {
//     // ...
//   });

declare module "vitest" {
  interface TestAPI {
    acceptance: (
      spec: string,
      scenario: string,
      fn: () => void | Promise<void>,
    ) => void;
  }
}

(test as unknown as { acceptance: TestAPI["acceptance"] }).acceptance = (
  spec: string,
  scenario: string,
  fn: () => void | Promise<void>,
) => {
  test(`[${spec}] ${scenario}`, fn);
};

type TestAPI = typeof test;
