// frontend/src/kinds/memory/frontmatter.test.ts
//
// Pin the leading-frontmatter split: parse `key: value` pairs and strip the
// block off the body; pass non-frontmatter text through unchanged.
import { describe, expect, test } from "vitest";
import { splitFrontmatter } from "./frontmatter";

describe("splitFrontmatter", () => {
  test("parses a leading frontmatter block and strips it from the body", () => {
    const { meta, body } = splitFrontmatter(
      "---\ntitle: Deploy\ndescription: how it ships\nupdated_at: 2026-06-22\n---\n# Body\ntext",
    );
    expect(meta.title).toBe("Deploy");
    expect(meta.description).toBe("how it ships");
    expect(meta.updated_at).toBe("2026-06-22");
    expect(body).toBe("# Body\ntext");
  });

  test("strips surrounding quotes from values", () => {
    const { meta } = splitFrontmatter('---\ntitle: "Quoted Title"\n---\nbody');
    expect(meta.title).toBe("Quoted Title");
  });

  test("returns the text unchanged when there is no frontmatter", () => {
    const { meta, body } = splitFrontmatter("# Just markdown\nno fences");
    expect(meta).toEqual({});
    expect(body).toBe("# Just markdown\nno fences");
  });

  test("does not treat a mid-document --- as frontmatter", () => {
    const text = "intro\n\n---\n\nrest";
    expect(splitFrontmatter(text).body).toBe(text);
  });
});
