import { describe, expect, test } from "vitest";

import { formatVersion } from "./version";

describe("formatVersion", () => {
  test("prefixes a bare version with v", () => {
    expect(formatVersion("1.0.0")).toBe("v1.0.0");
  });

  test("leaves a version that already starts with v alone", () => {
    expect(formatVersion("v1.0.0")).toBe("v1.0.0");
  });
});
