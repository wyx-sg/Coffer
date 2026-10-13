// frontend/src/lib/knowledge/fileLinks.ts
//
// A standard Markdown link between knowledge files (spec knowledge "Link
// pages by slug and check every link"): `[text](../other/page.md)`. A target
// with a URL scheme, or one starting with `#`, is external and opens as any
// link does; any other target is a path the daemon resolved relative to the
// file that holds it, and the file's read carries that resolution beside its
// wiki links (`kind: "markdown"`). This only matches a rendered href to it.
import type { LinkRefOut } from "@/lib/api/knowledge";

/** Whether `href` leaves the knowledge files: a URL scheme, or a `#` anchor. */
export function isExternalHref(href: string): boolean {
  return /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#");
}

function decoded(text: string): string {
  try {
    return decodeURI(text);
  } catch {
    return text;
  }
}

/** The file's resolution of a standard link written as `href`, if it has one. */
export function resolveFileLink(links: LinkRefOut[], href: string): LinkRefOut | undefined {
  const markdown = links.filter((link) => link.kind === "markdown");
  return (
    markdown.find((link) => link.target === href) ??
    markdown.find((link) => decoded(link.target) === decoded(href))
  );
}
