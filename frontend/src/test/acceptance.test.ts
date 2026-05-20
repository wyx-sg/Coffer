import { test, expect } from "vitest";

// Smoke tests for the `test.acceptance` helper installed by ./setup.ts.
// If vitest's `test` API changes in a way that breaks the helper assignment,
// these tests fail at CI time rather than the first real acceptance test.

test("test.acceptance helper is wired up", () => {
  expect(typeof test.acceptance).toBe("function");
});

test.acceptance(
  "__stub__",
  "stub helper produces a passing test",
  () => {
    expect(true).toBe(true);
  },
);
