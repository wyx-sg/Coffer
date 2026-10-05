// frontend/src/lib/preferences.test.ts
import { afterEach, describe, expect, test } from "vitest";
import { blockLocalStorage } from "@/test/blockedStorage";
import { getHandoffAgent, getPreferredEditor } from "./preferences";

afterEach(() => localStorage.clear());

describe("with storage blocked", () => {
  test.each(["access", "methods"] as const)(
    "reads fall back and writes do not throw (%s)",
    (mode) => {
      const restore = blockLocalStorage(mode);
      try {
        expect(getPreferredEditor()).toBe("");
        expect(getHandoffAgent()).toBe("");
      } finally {
        restore();
      }
    },
  );
});
