// frontend/src/lib/knowledge/wikiLinks.test.ts — finding a page's [[links]] outside code.
import { describe, expect, test } from "vitest";

import { markWikiLinks, resolveWikiLink, wikiTargetOf } from "./wikiLinks";

describe("markWikiLinks", () => {
  test("turns [[target]] and [[target|text]] into #wiki: links", () => {
    expect(markWikiLinks("See [[session-ownership]] and [[sessions|the session service]].")).toBe(
      "See [session-ownership](#wiki:session-ownership) and [the session service](#wiki:sessions).",
    );
  });

  test("leaves links inside code spans and fenced blocks as written", () => {
    const body = "Use `[[gone]]` here.\n\n```\n[[gone]]\n```\n\n~~~md\n[[gone]]\n~~~\n[[real]]";
    const out = markWikiLinks(body);
    expect(out).toContain("`[[gone]]`");
    expect(out.match(/#wiki:/g)).toHaveLength(1);
    expect(out).toContain("[real](#wiki:real)");
  });

  test("leaves a leading frontmatter block alone", () => {
    expect(markWikiLinks("---\ntitle: [[x]]\n---\n[[y]]")).toBe(
      "---\ntitle: [[x]]\n---\n[y](#wiki:y)",
    );
  });

  test("a target with parentheses survives the round trip", () => {
    const out = markWikiLinks("[[cache (ttl)]]");
    const href = /\((#wiki:[^)]*)\)/.exec(out)?.[1];
    expect(wikiTargetOf(href)).toBe("cache (ttl)");
  });
});

describe("resolveWikiLink", () => {
  test("matches a target case-insensitively", () => {
    const links = [{ target: "Session-Ownership", path: "c/pages/s.md", ambiguous: false }];
    expect(resolveWikiLink(links, "session-ownership")?.path).toBe("c/pages/s.md");
    expect(resolveWikiLink(links, "gone")).toBeUndefined();
    expect(wikiTargetOf("https://example.com")).toBeNull();
  });
});
