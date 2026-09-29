// frontend/src/lib/preview/frontmatter.test.ts
//
// Pin the leading-frontmatter split: top-level keys in order, block lists
// (including items that are small mappings), block scalars, and text that is
// not frontmatter passed through untouched.
import { describe, expect, test } from "vitest";

import { splitFrontmatter } from "./frontmatter";

describe("splitFrontmatter", () => {
  test("parses scalar keys in order and strips the block off the body", () => {
    const { entries, body } = splitFrontmatter(
      '---\ntitle: Deploy\ndescription: "how it ships"\nupdated_at: 2026-06-22\n---\n# Body\ntext',
    );
    expect(entries).toEqual([
      { key: "title", value: "Deploy" },
      { key: "description", value: "how it ships" },
      { key: "updated_at", value: "2026-06-22" },
    ]);
    expect(body).toBe("# Body\ntext");
  });

  test("a memory note's origins list comes out as a list, not as body text", () => {
    const { entries, body } = splitFrontmatter(
      [
        "---",
        "title: Build with uv",
        "origins:",
        "  - agent: claude_code",
        "    at: 2026-09-20",
        "  - agent: codex",
        "tags: [build, python]",
        "---",
        "Use `uv sync --frozen`.",
      ].join("\n"),
    );
    expect(entries).toEqual([
      { key: "title", value: "Build with uv" },
      { key: "origins", value: ["agent: claude_code, at: 2026-09-20", "agent: codex"] },
      { key: "tags", value: "[build, python]" },
    ]);
    expect(body).toBe("Use `uv sync --frozen`.");
  });

  test("a list written flush with its key is still that key's list", () => {
    const { entries } = splitFrontmatter("---\nsources:\n- a.md\n- b.md\n---\nx");
    expect(entries).toEqual([{ key: "sources", value: ["a.md", "b.md"] }]);
  });

  test("block scalars and nested mappings stay readable", () => {
    const { entries } = splitFrontmatter(
      "---\nsummary: |\n  line one\n  line two\nmeta:\n  owner: me\n  scope: global\n---\n",
    );
    expect(entries).toEqual([
      { key: "summary", value: "line one\nline two" },
      { key: "meta", value: ["owner: me", "scope: global"] },
    ]);
  });

  test("text with no leading fence is returned unchanged", () => {
    const text = "# Just markdown\n\n---\n\nrest";
    expect(splitFrontmatter(text)).toEqual({ entries: [], body: text });
  });

  test("a fenced block with no key in it is left in the body", () => {
    const text = "---\njust a sentence\n---\nbody";
    expect(splitFrontmatter(text)).toEqual({ entries: [], body: text });
  });

  test("an empty fence pair is removed", () => {
    expect(splitFrontmatter("---\n---\nbody")).toEqual({ entries: [], body: "body" });
  });

  test("CRLF line endings are handled", () => {
    const { entries, body } = splitFrontmatter("---\r\ntitle: T\r\n---\r\nbody");
    expect(entries).toEqual([{ key: "title", value: "T" }]);
    expect(body).toBe("body");
  });
});
