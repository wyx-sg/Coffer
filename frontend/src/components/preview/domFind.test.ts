// src/components/preview/domFind.test.ts
import { afterEach, describe, expect, test } from "vitest";
import { findRanges } from "./domFind";

function container(html: string): HTMLElement {
  const el = document.createElement("div");
  el.innerHTML = html;
  document.body.appendChild(el);
  return el;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("findRanges", () => {
  test("finds every occurrence across text nodes, in order", () => {
    const el = container("<p>foo bar foo</p><p>another foo</p>");
    const ranges = findRanges(el, "foo", false);
    expect(ranges).toHaveLength(3);
    expect(ranges.every((r) => r.toString() === "foo")).toBe(true);
  });

  test("is case-insensitive by default and case-sensitive on request", () => {
    const el = container("<p>Foo FOO foo</p>");
    expect(findRanges(el, "foo", false)).toHaveLength(3);
    const sensitive = findRanges(el, "foo", true);
    expect(sensitive).toHaveLength(1);
    expect(sensitive[0].toString()).toBe("foo");
  });

  test("returns nothing for a blank query", () => {
    const el = container("<p>anything</p>");
    expect(findRanges(el, "", false)).toHaveLength(0);
  });

  test("ignores text inside <script> and <style> nodes", () => {
    const el = container("<style>foo{}</style><p>foo</p><script>foo</script>");
    expect(findRanges(el, "foo", false)).toHaveLength(1);
  });

  test("handles overlapping-free repeated substrings without infinite loop", () => {
    const el = container("<p>aaaa</p>");
    // Non-overlapping scan: "aa" appears twice in "aaaa".
    expect(findRanges(el, "aa", false)).toHaveLength(2);
  });
});
