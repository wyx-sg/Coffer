// frontend/src/lib/knowledge/routes.ts
//
// The addresses of the one Knowledge page (router.tsx). The tree stays on the
// left whatever the right pane shows, and what it shows is always in the URL
// (.agents/frontend.md §3):
//
//   /knowledge                  every collection, nothing chosen
//   /knowledge/<uid>            a collection; `?file=` opens a document
//
// A collection is addressed by its immutable uid (spec web-ui "Lay out every
// detail page's tabs alike"); a document by its knowledge-root-relative path,
// which starts with the collection's directory NAME. A document has no tabs, so
// an address with any other path segment (an old `/<uid>/history?file=`) is sent
// to the bare address by the shared unknown-tab handling and opens the document.

/** The one view a collection address can name in its path: the default, never
 *  spelled out. Any other segment is unknown and is redirected away. */
export const KNOWLEDGE_TABS = ["document"] as const;
export const DEFAULT_KNOWLEDGE_TAB = "document";

export const KNOWLEDGE_ROOT = "/knowledge";

/** A collection's base address. */
export function collectionBasePath(uid: string): string {
  return `${KNOWLEDGE_ROOT}/${encodeURIComponent(uid)}`;
}

/** A collection's address, with an optional open file. */
export function collectionPath(uid: string, file?: string | null) {
  const query = file ? `?file=${encodeURIComponent(file)}` : "";
  return `${collectionBasePath(uid)}${query}`;
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
