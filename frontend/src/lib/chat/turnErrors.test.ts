// frontend/src/lib/chat/turnErrors.test.ts
import { describe, expect, test } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { describeTurnError, isAgentNotLoggedIn } from "./turnErrors";

// Mimics i18next: returns the key when no translation exists.
const t = (key: string) =>
  key === "chat.errors.agentNotLoggedIn" ? "LOGIN COPY" : key === "errors.BOOM" ? "boom copy" : key;

describe("isAgentNotLoggedIn", () => {
  test("matches the agent CLI's not-logged-in wording and a /login hint", () => {
    expect(isAgentNotLoggedIn(new Error("Not logged in. Please run claude"))).toBe(true);
    expect(isAgentNotLoggedIn(new ApiError("AGENT_ERROR", "run /login first"))).toBe(true);
    expect(isAgentNotLoggedIn("please /LOGIN")).toBe(true);
  });

  test("does not match other failures or empty input", () => {
    expect(isAgentNotLoggedIn(new Error("rate limited"))).toBe(false);
    expect(isAgentNotLoggedIn(null)).toBe(false);
    expect(isAgentNotLoggedIn(undefined)).toBe(false);
  });
});

describe("describeTurnError", () => {
  test("maps a not-logged-in failure to the actionable copy, ahead of any error code", () => {
    expect(describeTurnError(t, new ApiError("BOOM", "not logged in"))).toBe("LOGIN COPY");
  });

  test("falls back to translateApiError for everything else", () => {
    expect(describeTurnError(t, new ApiError("BOOM", "raw"))).toBe("boom copy");
    expect(describeTurnError(t, new ApiError("UNKNOWN_X", "raw message"))).toBe("raw message");
    expect(describeTurnError(t, new Error("plain"))).toBe("plain");
  });
});
