// frontend/src/lib/credentialRef.test.ts
//
// The shape of a credential ref, and the ownership test that reads it back.
// Both used to be derived from the resource's name, which is what made a
// rename able to strand a secret; these assertions are the statement that
// nothing mutable gets into an address any more.
import { describe, expect, test } from "vitest";

import { isMintedCredentialRef, mintCredentialRef } from "./credentialRef";

describe("mintCredentialRef", () => {
  test("is `<kind>/<uuid4 hex>/<logical key>`", () => {
    expect(mintCredentialRef("channel", "bot-token")).toMatch(/^channel\/[0-9a-f]{32}\/bot-token$/);
    expect(mintCredentialRef("mcp_server", "GITHUB_TOKEN")).toMatch(
      /^mcp_server\/[0-9a-f]{32}\/GITHUB_TOKEN$/,
    );
  });

  test("really is a version-4 uuid, not sixteen random bytes wearing its shape", () => {
    const body = mintCredentialRef("channel", "bot-token").split("/")[1];
    expect(body[12]).toBe("4");
    expect("89ab").toContain(body[16]);
  });

  test("mints a fresh address every call", () => {
    // Fresh per SECRET is the rule provider follows, and it is why a rotation
    // has to reuse the ref already in the config rather than call this again.
    const many = new Set(Array.from({ length: 50 }, () => mintCredentialRef("channel", "x")));
    expect(many.size).toBe(50);
  });

  test("the only thing a caller puts in is the logical key", () => {
    // There is no name parameter to pass, which is the point: nothing a user
    // can rename can reach the address. The tail is the secret's own role.
    expect(mintCredentialRef("channel", "signing-secret").endsWith("/signing-secret")).toBe(true);
  });
});

describe("isMintedCredentialRef", () => {
  test("recognises what it minted, for that kind only", () => {
    const ref = mintCredentialRef("mcp_server", "TOKEN");
    expect(isMintedCredentialRef("mcp_server", ref)).toBe(true);
    // Kinds do not claim each other's addresses — the MCP edit dialog's orphan
    // cleanup would otherwise delete a channel's secret.
    expect(isMintedCredentialRef("channel", ref)).toBe(false);
  });

  test("never claims a ref a person wrote", () => {
    // These are the refs the cleanup must leave alone: hand-written ones, and
    // the legacy name-derived shapes a vault may still hold where the secret
    // was never stored (migration 0093 leaves those exactly as they are).
    for (const foreign of [
      "smart.SMART_PAT",
      "channel/tg/bot-token",
      "my-token",
      "provider/1b2c3d4e5f60718293a4b5c6d7e8f900/key",
      "mcp_server/NOT-HEX-0000000000000000000000/TOKEN",
      "mcp_server/1b2c3d4e5f60718293a4b5c6d7e8f900",
    ]) {
      expect(isMintedCredentialRef("mcp_server", foreign)).toBe(false);
    }
  });
});
