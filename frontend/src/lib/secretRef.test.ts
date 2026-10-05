// frontend/src/lib/secretRef.test.ts
//
// The shape of a minted secret ref: `secret/<uuid4 hex>`, nothing mutable in the address.
import { describe, expect, test } from "vitest";

import { mintSecretRef, uuid4Hex } from "./secretRef";

describe("mintSecretRef", () => {
  test("is `secret/<uuid4 hex>`", () => {
    expect(mintSecretRef()).toMatch(/^secret\/[0-9a-f]{32}$/);
  });

  test("really is a version-4 uuid, not sixteen random bytes wearing its shape", () => {
    const body = uuid4Hex();
    expect(body[12]).toBe("4");
    expect("89ab").toContain(body[16]);
  });

  test("mints a fresh address every call", () => {
    // Fresh per SECRET, which is why a rotation has to reuse the ref already in the config.
    const many = new Set(Array.from({ length: 50 }, () => mintSecretRef()));
    expect(many.size).toBe(50);
  });
});
