// frontend/src/lib/secretRef.test.ts
//
// The shape of a secret ref, and the ownership test that reads it back.
import { describe, expect, test } from "vitest";

import { isOwnRef, mintSecretRef, refSegment } from "./secretRef";

describe("refSegment", () => {
  test("keeps [A-Za-z0-9_.-] and replaces everything else with a dash", () => {
    expect(refSegment("my-bot_1.2")).toBe("my-bot_1.2");
    expect(refSegment("My Bot/é")).toBe("My-Bot--");
  });

  test("strips leading dots and never comes back empty", () => {
    expect(refSegment("..hidden")).toBe("hidden");
    expect(refSegment("...")).toBe("x");
    expect(refSegment("")).toBe("x");
  });
});

describe("mintSecretRef", () => {
  test("is `<kind>/<name segment>/<slot>`", () => {
    expect(mintSecretRef("channel", "tg", "bot-token")).toBe("channel/tg/bot-token");
    expect(mintSecretRef("mcp_server", "my github", "GITHUB_TOKEN")).toBe(
      "mcp_server/my-github/GITHUB_TOKEN",
    );
  });
});

describe("isOwnRef", () => {
  test("recognises a ref named for this resource, for that kind only", () => {
    const ref = mintSecretRef("mcp_server", "github", "TOKEN");
    expect(isOwnRef("mcp_server", "github", ref)).toBe(true);
    expect(isOwnRef("channel", "github", ref)).toBe(false);
    expect(isOwnRef("mcp_server", "gitlab", ref)).toBe(false);
  });

  test("accepts the -<n> collision suffix and normalised names", () => {
    expect(isOwnRef("mcp_server", "github", "mcp_server/github-2/TOKEN")).toBe(true);
    expect(isOwnRef("mcp_server", "my github", "mcp_server/my-github/TOKEN")).toBe(true);
  });

  test("never claims a ref a person wrote or another resource owns", () => {
    for (const foreign of [
      "smart.SMART_PAT",
      "my-token",
      "provider/github/key",
      "mcp_server/github-extra/TOKEN",
      "mcp_server/github",
    ]) {
      expect(isOwnRef("mcp_server", "github", foreign)).toBe(false);
    }
  });

  test("escapes regex characters in the name", () => {
    expect(isOwnRef("mcp_server", "a.b", "mcp_server/axb/TOKEN")).toBe(false);
    expect(isOwnRef("mcp_server", "a.b", "mcp_server/a.b/TOKEN")).toBe(true);
  });
});
