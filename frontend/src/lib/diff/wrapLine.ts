// frontend/src/lib/diff/wrapLine.ts
//
// Cuts one long diff line into rows for FileDiff, the one diff renderer (Foundations 0.6.05):
// nothing is truncated, the view shows each continuation under a ↳.

/** Characters per row before a line wraps: a typical detail pane at 12px mono. */
const WRAP_AT = 84;

/** A line cut into rows of at most `width` characters, at a space where there
 *  is one; continuation rows are indented two spaces, as on the board. */
export function wrapLine(text: string, width = WRAP_AT): string[] {
  if (text.length <= width) return [text];
  const out: string[] = [];
  let rest = text;
  let first = true;
  while (rest.length > (first ? width : width - 2)) {
    const room = first ? width : width - 2;
    const cut = rest.lastIndexOf(" ", room);
    const at = cut > room / 2 ? cut : room;
    out.push((first ? "" : "  ") + rest.slice(0, at));
    rest = rest.slice(at).replace(/^ /, "");
    first = false;
  }
  out.push((first ? "" : "  ") + rest);
  return out;
}
