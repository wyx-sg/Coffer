// src/test/truncatedPath.ts — a text matcher for a TruncatedPath, whose text is split into head and last segment.
/** `getByText(pathText("~/a/b"))` finds the one TruncatedPath showing that path. */
export function pathText(path: string) {
  return (_content: string, el: Element | null): boolean =>
    Boolean(el?.hasAttribute("data-truncated-path")) && el?.textContent === path;
}
