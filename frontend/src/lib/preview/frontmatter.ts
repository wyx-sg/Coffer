// frontend/src/lib/preview/frontmatter.ts
//
// Splits a Markdown file's leading YAML frontmatter off its body, so a preview
// can show it as metadata above the text rather than render it AS text.
// Rendered raw, the `---` fences become rules and `title: … origins: - …`
// becomes a paragraph and a bullet list, which reads as if it were part of the
// note (spec knowledge "Show a collection as one tree of read-only documents in the web UI").
//
// A tiny hand-written reader for the subset Coffer's own files and agents'
// files actually use — `key: value`, a block list under a key (`- item`, where
// an item may itself be a small mapping), a nested mapping, a `|` / `>` block
// scalar — not a YAML implementation. Anything it does not understand still
// comes out as text under its key: the point is to keep metadata out of the
// body, not to interpret it. Text that does not open with a fence, or whose
// fenced block holds no `key:` line, is returned untouched.

/** One top-level frontmatter key, in file order. A block list is an array. */
export interface FrontmatterEntry {
  key: string;
  value: string | string[];
}

interface SplitFrontmatter {
  /** The frontmatter's top-level keys, in order; empty when there is none. */
  entries: FrontmatterEntry[];
  /** The Markdown with any leading frontmatter block removed. */
  body: string;
}

// A leading `---` line, the block, and a closing `---` line. The block may be
// empty (`---\n---`).
const FENCE_RE = /^---[ \t]*\r?\n(?:([\s\S]*?)\r?\n)?---[ \t]*(?:\r?\n|$)/;
const KEY_RE = /^([A-Za-z0-9_][\w.-]*)\s*:(?:\s+(.*))?$/;
const ITEM_RE = /^\s*-(?:\s+(.*))?$/;

function unquote(value: string): string {
  const v = value.trim();
  if (v.length >= 2 && ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'")))) {
    return v.slice(1, -1);
  }
  return v;
}

/** The lines indented under one key, turned into a list or a text value. */
function readNested(lines: string[], scalar: string): string | string[] {
  const content = lines.filter((l) => l.trim() !== "" && !l.trim().startsWith("#"));
  // A block scalar: the indented lines ARE the value.
  if (/^[|>][+-]?$/.test(scalar)) {
    return content.map((l) => l.trim()).join(scalar.startsWith("|") ? "\n" : " ");
  }
  if (content.length === 0) return unquote(scalar);

  // A list, possibly of small mappings: each `- ` opens an item, and a deeper
  // line continues the one before it.
  if (ITEM_RE.test(content[0])) {
    const items: string[] = [];
    for (const line of content) {
      const item = ITEM_RE.exec(line);
      if (item) items.push(unquote(item[1] ?? ""));
      else if (items.length > 0) {
        const last = items.length - 1;
        items[last] = items[last] ? `${items[last]}, ${line.trim()}` : line.trim();
      }
    }
    return items;
  }
  // A nested mapping (or anything else indented): one line each.
  return content.map((l) => l.trim());
}

export function splitFrontmatter(text: string): SplitFrontmatter {
  const match = FENCE_RE.exec(text);
  if (!match) return { entries: [], body: text };
  const block = match[1] ?? "";
  const body = text.slice(match[0].length);

  const entries: FrontmatterEntry[] = [];
  let current: { key: string; scalar: string; nested: string[] } | null = null;
  const flush = () => {
    if (current)
      entries.push({ key: current.key, value: readNested(current.nested, current.scalar) });
  };

  for (const line of block.split(/\r?\n/)) {
    const isIndented = /^\s/.test(line) || (ITEM_RE.test(line) && current !== null);
    if (!isIndented) {
      const key = KEY_RE.exec(line);
      if (key) {
        flush();
        current = { key: key[1], scalar: (key[2] ?? "").trim(), nested: [] };
        continue;
      }
    }
    if (current && line.trim() !== "") current.nested.push(line);
  }
  flush();

  // A fenced block with no key in it is not frontmatter we can show; leave the
  // text alone rather than silently dropping it. An empty block is still a
  // fence pair, and still not body.
  if (entries.length === 0 && block.trim() !== "") return { entries: [], body: text };
  return { entries, body };
}
