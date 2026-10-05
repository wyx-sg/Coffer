// frontend/src/lib/knowledge/titleHeading.ts
//
// The reader shows a document's title itself (board 5.1.01), so a body that
// opens with its own `# Heading` line must not put a second title under it.
// That heading is what the author wrote at the top of the text, often a
// longer form of the frontmatter's `title` ("X — Y" over "X — Y, and Z"), so
// it is the one shown, in the title's place, and the body starts after it.

/** The one title the reader shows, and the body under it. */
export function splitTitleHeading(body: string, title: string): { title: string; body: string } {
  const match = /^\s*#[ \t]+(.+?)[ \t#]*\r?\n+/.exec(body);
  if (!match) return { title, body };
  return { title: match[1].trim(), body: body.slice(match[0].length) };
}
