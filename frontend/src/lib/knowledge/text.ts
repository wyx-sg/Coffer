// frontend/src/lib/knowledge/text.ts
// Small pieces of wording the Knowledge page derives rather than stores: the
// description an item added from the web UI carries (the daemon requires one;
// the dialog has no field for it).

/** The body's first sentence (headings skipped, up to 160 characters), or the
 *  title when the body has none. */
export function describeItem(title: string, body: string): string {
  const text = body
    .replace(/^#+\s.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  const sentence = text.split(/(?<=[.!?。！？])\s/)[0] ?? "";
  return (sentence || title).slice(0, 160);
}
