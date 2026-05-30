// frontend/src/lib/preferences.test.ts
import { afterEach, describe, expect, test } from "vitest";
import { PAGE_SIZE_OPTIONS, getDefaultPageSize, setDefaultPageSize } from "./preferences";

afterEach(() => localStorage.clear());

describe("default page-size preference", () => {
  test("defaults to 20 when unset", () => {
    expect(getDefaultPageSize()).toBe(20);
  });

  test("round-trips a valid option through localStorage", () => {
    setDefaultPageSize(50);
    expect(getDefaultPageSize()).toBe(50);
    expect(localStorage.getItem("coffer.pageSize")).toBe("50");
  });

  test("ignores a stored value outside the allowed options", () => {
    localStorage.setItem("coffer.pageSize", "999");
    expect(getDefaultPageSize()).toBe(20);
  });

  test("exposes the canonical option set", () => {
    expect([...PAGE_SIZE_OPTIONS]).toEqual([10, 20, 50, 100]);
  });
});
