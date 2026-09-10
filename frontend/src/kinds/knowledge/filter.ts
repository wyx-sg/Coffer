// frontend/src/kinds/knowledge/filter.ts
//
// The one matcher behind both lanes' filter box. Filtering is CLIENT-SIDE and
// name-only: it narrows the list already on screen as the user types — no
// request, no debounce, no ranking. Meaning-based retrieval over a scope's
// bodies is the agents' surface (`coffer__search`) and the CLI's.

/** Case-insensitive substring match over a file's title and its basename. */
export function matchesFilter(filter: string, title: string, path?: string | null): boolean {
  const needle = filter.trim().toLowerCase();
  if (!needle) return true;
  const basename = path ? (path.split("/").pop() ?? "") : "";
  return title.toLowerCase().includes(needle) || basename.toLowerCase().includes(needle);
}
