// frontend/src/lib/knowledge/wikiLinks.ts
//
// A page's `[[target]]` and `[[target|text]]` links (spec knowledge "Link
// pages by slug and check every link"), made renderable: outside code spans
// and fenced blocks each becomes an ordinary Markdown link whose href carries
// the target behind a `#wiki:` marker, so the reader's link element can look
// it up in the page's resolved `links` and open the file it names — or mark it
// dead or ambiguous. The daemon resolves the links; this only finds them in
// the text the same way it does and matches a target to its resolution.
import type { LinkRefOut } from "@/lib/api/knowledge";

const WIKI_HREF = "#wiki:";
const WIKI_LINK = /\[\[([^[\]|\n]+?)(?:\|([^[\]\n]+?))?\]\]/g;
const FENCE = /^ {0,3}(`{3,}|~{3,})/;

/** Text safe inside a Markdown link's brackets. */
function escapeText(text: string): string {
  return text.replace(/[[\]\\]/g, "\\$&");
}

/** A target as a link destination that Markdown and the URL check both keep. */
function encodeTarget(target: string): string {
  return encodeURIComponent(target).replace(
    /[()]/g,
    (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
  );
}

function linkLine(line: string): string {
  // Odd parts are code spans, left as written.
  return line
    .split(/(`+[^`]*`+)/)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(WIKI_LINK, (_m, target: string, text?: string) => {
            const name = target.trim();
            return `[${escapeText((text ?? target).trim())}](${WIKI_HREF}${encodeTarget(name)})`;
          }),
    )
    .join("");
}

/** The body with every `[[link]]` outside code turned into a `#wiki:` link. */
export function markWikiLinks(body: string): string {
  const lines = body.split("\n");
  let fence: string | null = null;
  // A leading frontmatter block is metadata, not text with links.
  let frontmatter = lines[0] === "---";
  return lines
    .map((line, i) => {
      if (frontmatter) {
        if (i > 0 && line === "---") frontmatter = false;
        return line;
      }
      const open = FENCE.exec(line);
      if (fence !== null) {
        if (open && open[1][0] === fence[0] && open[1].length >= fence.length) fence = null;
        return line;
      }
      if (open) {
        fence = open[1];
        return line;
      }
      return linkLine(line);
    })
    .join("\n");
}

/** The target a rendered link's href carries, or null for an ordinary link. */
export function wikiTargetOf(href: string | undefined): string | null {
  if (!href?.startsWith(WIKI_HREF)) return null;
  try {
    return decodeURIComponent(href.slice(WIKI_HREF.length));
  } catch {
    return href.slice(WIKI_HREF.length);
  }
}

function normalise(target: string): string {
  return target.normalize("NFKC").trim().toLowerCase();
}

/** The page's resolution of `target`, matched as the daemon matches it. */
export function resolveWikiLink(links: LinkRefOut[], target: string): LinkRefOut | undefined {
  const key = normalise(target);
  return links.find((link) => normalise(link.target) === key);
}
