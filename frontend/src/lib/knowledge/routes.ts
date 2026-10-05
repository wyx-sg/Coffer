// frontend/src/lib/knowledge/routes.ts
//
// The addresses of the one Knowledge page (router.tsx). The tree stays on the
// left whatever the right pane shows, and what it shows is always in the URL
// (.agents/frontend.md §3):
//
//   /knowledge                           every collection, nothing chosen
//   /knowledge/<uid>                     a collection; `?file=` opens a document
//   /knowledge/<uid>/history?file=<path> that document's History tab
//
// A collection is addressed by its immutable uid (spec web-ui "Lay out every
// detail page's tabs alike"); a document by its knowledge-root-relative path,
// which starts with the collection's directory NAME. A document's tab is the
// path segment: Document, the default, is never spelled out; any other segment
// is sent to the bare address by the shared unknown-tab handling.

/** A document's tabs, the default first. */
export const KNOWLEDGE_TABS = ["document", "history"] as const;
export type KnowledgeTab = (typeof KNOWLEDGE_TABS)[number];
export const DEFAULT_KNOWLEDGE_TAB: KnowledgeTab = "document";

export const KNOWLEDGE_ROOT = "/knowledge";

/** A collection's base address. */
export function collectionBasePath(uid: string): string {
  return `${KNOWLEDGE_ROOT}/${encodeURIComponent(uid)}`;
}

/** A collection's address, with an optional open file on one of its tabs. */
export function collectionPath(
  uid: string,
  file?: string | null,
  tab: KnowledgeTab = DEFAULT_KNOWLEDGE_TAB,
) {
  const query = file ? `?file=${encodeURIComponent(file)}` : "";
  const segment = tab === DEFAULT_KNOWLEDGE_TAB ? "" : `/${tab}`;
  return `${collectionBasePath(uid)}${segment}${query}`;
}

/** A path with its collection segment removed (`coffer/daemon/port.md` →
 *  `daemon/port.md`), for a row that already names the collection. */
export function pathInCollection(path: string): string {
  const i = path.indexOf("/");
  return i < 0 ? path : path.slice(i + 1);
}

/** Where a knowledge-root-relative path lives in the vault: knowledge is the
 *  vault's `knowledge/` directory, one folder per collection. */
export function vaultPathOf(path: string): string {
  return `knowledge/${path}`;
}
