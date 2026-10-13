// frontend/src/lib/knowledge/pathLinks.ts
//
// A knowledge file's ordinary Markdown links (spec knowledge "Link pages by
// slug or relative path and check every link"), sorted the way the reader
// opens them: a web link goes to the browser, a link by relative path to the
// file it names inside the knowledge root — checked by the daemon (the file's
// `links`, kind `path`) — and an anchor stays on the page.
import type { LinkRefOut } from "@/lib/api/knowledge";
import { resolveAsset } from "@/lib/knowledge/assets";

const SCHEME = /^[a-z][a-z0-9+.-]*:/i;
const WEB = /^(https?:|mailto:)/i;

/** Whether `href` is a web link the browser opens. */
export function isWebLink(href: string | undefined): boolean {
  return Boolean(href && WEB.test(href.trim()));
}

/** The file a link names, as the daemon writes a link's target: the path
 *  without its query or anchor, decoded. `null` for a scheme, `//host` or an
 *  anchor alone. */
export function pathTargetOf(href: string | undefined): string | null {
  const dest = href?.trim();
  if (!dest || dest.startsWith("#") || dest.startsWith("//") || SCHEME.test(dest)) return null;
  const path = dest.split(/[?#]/)[0];
  try {
    return decodeURIComponent(path) || null;
  } catch {
    return path || null;
  }
}

export type PathLink =
  | { state: "file"; path: string }
  | { state: "dead"; target: string }
  | { state: "outside"; target: string };

/** Where a relative link in the file at `documentPath` goes: the daemon's
 *  resolution when it checked the link, else the path read the way any
 *  Markdown reader would (a link the daemon does not see, inside HTML). */
export function resolvePathLink(
  links: LinkRefOut[],
  documentPath: string,
  target: string,
): PathLink {
  const checked = links.find((link) => link.kind === "path" && link.target === target);
  if (checked) {
    if (checked.path) return { state: "file", path: checked.path };
    return { state: checked.outside ? "outside" : "dead", target };
  }
  const path = resolveAsset(documentPath, encodeURI(target));
  return path ? { state: "file", path } : { state: "outside", target };
}
