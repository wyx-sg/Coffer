// frontend/src/lib/knowledge/titleHeading.ts
//
// The reader shows a document's title itself (board 5.1.01), so a body that
// opens with the same `# Title` line must not say it twice.
/** The body without a leading `# Title` line that only repeats the title above it. */
export function withoutTitleHeading(body: string, title: string): string {
  const match = /^\s*#[ \t]+(.+?)[ \t]*\r?\n+/.exec(body);
  return match && match[1].trim() === title.trim() ? body.slice(match[0].length) : body;
}
