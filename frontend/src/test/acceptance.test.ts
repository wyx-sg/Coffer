import { test, expect } from "vitest";
import { acceptance } from "./acceptance";

// Smoke tests for the acceptance helper.
// If the helper signature or runtime wrapper changes in a way that breaks
// downstream usage, these fail at unit-tier rather than at the first real
// acceptance test.

test("acceptance helper is callable", () => {
  expect(typeof acceptance).toBe("function");
});

acceptance("__stub__", "stub helper produces a passing test", () => {
  expect(true).toBe(true);
});
