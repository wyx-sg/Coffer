import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins multiple class names with spaces", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("dedupes conflicting tailwind utilities, keeping the latter", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("drops falsy values", () => {
    expect(cn("foo", false, null, undefined, "bar")).toBe("foo bar");
  });

  it("flattens nested arrays via clsx", () => {
    expect(cn(["foo", "bar"], ["baz"])).toBe("foo bar baz");
  });
});
