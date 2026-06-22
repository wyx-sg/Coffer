// frontend/src/kinds/memory/frontmatter.ts
//
// Tiny helper for the memory preview surfaces. Some memory files begin with a
// YAML frontmatter block (`---\n...\n---\n`). Rendered raw through Markdown the
// `---` fences become <hr> and the `key: value` lines dump as plain text, which
// reads badly. This splits a leading frontmatter block off the body so the
// preview can show its `title`/`description` (and a small meta line) as a clean
// header and pass only the body to <FindableMarkdown>. Naive on purpose: a
// regex for the leading fence + a `key: value` line parse — no YAML lib. Files
// without frontmatter are returned unchanged (meta is empty).
export interface SplitFrontmatter {
  /** Parsed `key: value` pairs from the leading frontmatter block (may be empty). */
  meta: Record<string, string>;
  /** The Markdown body with any leading frontmatter block stripped. */
  body: string;
}

// Matches a leading `---\n … \n---\n?` block at the very start of the text.
const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/;

export function splitFrontmatter(text: string): SplitFrontmatter {
  const match = FRONTMATTER_RE.exec(text);
  if (!match) return { meta: {}, body: text };

  const meta: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const idx = line.indexOf(":");
    if (idx <= 0) continue; // skip blank lines / lines without a key
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    // Strip surrounding quotes a writer may have added around the value.
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) meta[key] = value;
  }

  return { meta, body: text.slice(match[0].length) };
}
