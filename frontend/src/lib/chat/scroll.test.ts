import { describe, expect, test } from "vitest";

import { isNearBottom } from "./scroll";

describe("isNearBottom", () => {
  test("true when scrolled to the very bottom", () => {
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 800, clientHeight: 200 })).toBe(true);
  });

  test("true when within the threshold of the bottom", () => {
    // 1000 - 740 - 200 = 60 <= 80
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 740, clientHeight: 200 })).toBe(true);
  });

  test("false when scrolled up beyond the threshold (reading history)", () => {
    // 1000 - 300 - 200 = 500 > 80
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 300, clientHeight: 200 })).toBe(false);
  });

  test("respects a custom threshold", () => {
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 500, clientHeight: 200 }, 400)).toBe(true);
  });
});
