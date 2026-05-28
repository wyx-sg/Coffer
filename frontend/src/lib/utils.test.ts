import { describe, expect, it } from "vitest";
import { cn, formatDateTime } from "./utils";

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

describe("formatDateTime", () => {
  it("formats a valid ISO timestamp as YYYY-MM-DD HH:mm:ss in local time", () => {
    const result = formatDateTime("2026-05-28T09:30:45Z");
    // Local-time padded — exact value depends on TZ, but should be 19 chars
    // matching the YYYY-MM-DD HH:mm:ss shape.
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  });

  it("returns the raw input on an invalid ISO instead of NaN-NaN-NaN NaN:NaN:NaN", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
  });

  it("returns the raw input on an empty string", () => {
    expect(formatDateTime("")).toBe("");
  });
});
