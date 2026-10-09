// frontend/src/lib/knowledge/routes.ts
//
// The addresses of the one Knowledge page (router.tsx). The tree stays on the
// left whatever the right pane shows, and what it shows is always in the URL
// (.agents/frontend.md §3):
//
//   /knowledge                               every collection, nothing chosen
//   /knowledge/<uid>                         a collection; `?file=` opens a file
//   /knowledge/<uid>?file=<path>&history=1   that file with its history drawer
//
// A collection is addressed by its immutable uid (spec web-ui "Lay out every
// detail page's tabs alike"); a file by its knowledge-root-relative path,
// which starts with the collection's directory NAME. A file's pane has no
// tabs: its history is a drawer beside it, named by `history=1`. The address a
// History tab once had (`/knowledge/<uid>/history?file=`) is sent to the
// drawer, and any other trailing segment to the bare address
// (`legacyRedirect`).

export const KNOWLEDGE_ROOT = "/knowledge";

/** The search parameter that opens a file's history drawer. */
export const HISTORY_PARAM = "history";

/** A collection's base address. */
function collectionBasePath(uid: string): string {
  return `${KNOWLEDGE_ROOT}/${encodeURIComponent(uid)}`;
}

/** A collection's address, with an optional open file, and its history drawer. */
export function collectionPath(
  uid: string,
  file?: string | null,
  { history = false }: { history?: boolean } = {},
): string {
  if (!file) return collectionBasePath(uid);
  const drawer = history ? `&${HISTORY_PARAM}=1` : "";
  return `${collectionBasePath(uid)}?file=${encodeURIComponent(file)}${drawer}`;
}

/** Where an address with a trailing path segment goes: `/history` opens the
 *  file's history drawer, any other segment the bare address. */
export function legacyRedirect(uid: string, segment: string, search: string): string {
  const file = new URLSearchParams(search).get("file");
  return collectionPath(uid, file, { history: segment === "history" });
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
