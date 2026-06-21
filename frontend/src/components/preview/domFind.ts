// src/components/preview/domFind.ts
// Find-in-rendered-text for Markdown previews. Matches are located across the
// container's text nodes and painted with the CSS Custom Highlight API, which
// styles ranges WITHOUT mutating the DOM — so it never fights react-markdown's
// re-renders (the trade-off vs. wrapping matches in <mark>). findRanges() is the
// pure, testable core; highlight painting degrades gracefully where the API is
// absent (older webviews / jsdom). CodeMirror previews use findHighlight.ts.

const MATCH = "coffer-find";
const ACTIVE = "coffer-find-active";

// The CSS Custom Highlight API is not in every TS DOM lib version; reach it
// through narrow local shapes instead of `any` so the file stays strict-clean.
interface HighlightCtor {
  new (...ranges: Range[]): unknown;
}
interface HighlightRegistryLike {
  set(name: string, highlight: unknown): void;
  delete(name: string): void;
}

function registry(): HighlightRegistryLike | null {
  if (typeof CSS === "undefined") return null;
  const reg = (CSS as unknown as { highlights?: HighlightRegistryLike }).highlights;
  return reg ?? null;
}

function highlightCtor(): HighlightCtor | null {
  const ctor = (globalThis as unknown as { Highlight?: HighlightCtor }).Highlight;
  return ctor ?? null;
}

/** True when the running engine can paint highlights (real WebKit/Chromium). */
export function highlightsSupported(): boolean {
  return registry() !== null && highlightCtor() !== null;
}

/** All occurrences of `query` within the container's text nodes, in order. */
export function findRanges(container: HTMLElement, query: string, caseSensitive: boolean): Range[] {
  const ranges: Range[] = [];
  if (!query) return ranges;
  const needle = caseSensitive ? query : query.toLowerCase();
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      const tag = parent.tagName;
      if (tag === "SCRIPT" || tag === "STYLE") return NodeFilter.FILTER_REJECT;
      return node.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  let node = walker.nextNode();
  while (node) {
    const text = node.nodeValue ?? "";
    const haystack = caseSensitive ? text : text.toLowerCase();
    let i = haystack.indexOf(needle);
    while (i !== -1) {
      const range = document.createRange();
      range.setStart(node, i);
      range.setEnd(node, i + needle.length);
      ranges.push(range);
      i = haystack.indexOf(needle, i + needle.length);
    }
    node = walker.nextNode();
  }
  return ranges;
}

/** Paint all matches, distinguishing the active one; no-op without API support. */
export function applyHighlights(ranges: Range[], active: number): void {
  const reg = registry();
  const Highlight = highlightCtor();
  if (!reg || !Highlight) return;
  const others = ranges.filter((_, i) => i !== active);
  reg.set(MATCH, new Highlight(...others));
  if (active >= 0 && ranges[active]) reg.set(ACTIVE, new Highlight(ranges[active]));
  else reg.delete(ACTIVE);
}

/** Remove all find highlights. */
export function clearHighlights(): void {
  const reg = registry();
  if (!reg) return;
  reg.delete(MATCH);
  reg.delete(ACTIVE);
}

/** Scroll a match into view within its nearest scrollable ancestor. */
export function scrollRangeIntoView(range: Range | undefined): void {
  range?.startContainer.parentElement?.scrollIntoView({ block: "nearest" });
}
