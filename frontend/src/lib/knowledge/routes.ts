// frontend/src/lib/knowledge/routes.ts
//
// The addresses of the one Knowledge page (router.tsx). The tree stays on the
// left whatever the right pane shows, and what it shows is always in the URL
// (.agents/frontend.md §3):
//
//   /knowledge                              Recent changes, every collection
//   /knowledge/<uid>                        a collection; `?file=` opens a document
//   /knowledge/<uid>/history?file=<path>    that document's History tab
//
// A collection is addressed by its immutable uid (spec web-ui "Lay out every
// detail page's tabs alike"); a document by its knowledge-root-relative path,
// which starts with the collection's directory NAME.

/** The pane tabs a collection address can carry in its path. `document` is the
 *  default and is never spelled out. */
export const KNOWLEDGE_TABS = ["document", "history"] as const;
export type KnowledgeTab = (typeof KNOWLEDGE_TABS)[number];
export const DEFAULT_KNOWLEDGE_TAB: KnowledgeTab = "document";

export const KNOWLEDGE_ROOT = "/knowledge";

/** A collection's base address. */
export function collectionBasePath(uid: string): string {
  return `${KNOWLEDGE_ROOT}/${encodeURIComponent(uid)}`;
}

/** A collection's address on `tab`, with an optional open file. */
export function collectionPath(uid: string, tab: KnowledgeTab = "document", file?: string | null) {
  const segment = tab === DEFAULT_KNOWLEDGE_TAB ? "" : `/${tab}`;
  const query = file ? `?file=${encodeURIComponent(file)}` : "";
  return `${collectionBasePath(uid)}${segment}${query}`;
}

/** The collection a knowledge-root-relative path lives in: its first segment. */
export function collectionOfPath(path: string): string {
  return path.split("/")[0] ?? "";
}

/** A path with its collection segment removed (`coffer/daemon/port.md` →
 *  `daemon/port.md`), for a row that already names the collection. */
export function pathInCollection(path: string): string {
  const i = path.indexOf("/");
  return i < 0 ? path : path.slice(i + 1);
}
