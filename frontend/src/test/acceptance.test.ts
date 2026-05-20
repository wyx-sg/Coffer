import { test, expect } from "vitest";
import { acceptance } from "./acceptance";

// Smoke test for the acceptance helper. Verifies the export exists and is
// callable. We deliberately do NOT invoke `acceptance(spec, scenario, fn)`
// with literal strings here because `scripts/audit_acceptance.py` would
// match it as a real acceptance marker and flag it as an orphan once the
// first real spec lands. The standalone-function design has no runtime
// mutation to verify, so the typeof check is sufficient.

test("acceptance helper is callable", () => {
  expect(typeof acceptance).toBe("function");
});
