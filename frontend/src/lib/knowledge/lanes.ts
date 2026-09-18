// frontend/src/lib/knowledge/lanes.ts
//
// The two lanes a collection is made of, and the path arithmetic around them.
//
// A lane is a PATH SEGMENT, not a field: `shopee/sources/gw.md` is a source and
// `shopee/topics/account-gateway.md` is a topic document, and the segment is
// what decides who may write there (spec knowledge, invariant 2). The UI reads
// it back off the path rather than carrying a lane in state, so a deep link to
// a file is enough to know which half of the page it belongs to.

/** The two lanes a collection holds. */
export type KnowledgeLane = "sources" | "topics";

/** `true` for a lane name the layer knows. */
export function isKnowledgeLane(value: string | null | undefined): value is KnowledgeLane {
  return value === "sources" || value === "topics";
}

/**
 * The root of one lane, relative to the knowledge root (`shopee/sources`).
 *
 * `""` for a collection whose name is not known yet — the detail page is
 * addressed by uid and resolves the name from the resource read, so there is a
 * moment before it has one. An empty path is what the tree's query treats as
 * "nothing to ask for"; building `"/sources"` instead would fire a request for
 * a directory that cannot exist.
 */
export function lanePath(collection: string, lane: KnowledgeLane): string {
  return collection === "" ? "" : `${collection}/${lane}`;
}

/**
 * The lane a knowledge path belongs to, or `null` when it names neither —
 * a `README.md` at a collection's root, say, which is outside both (FR-007).
 */
function laneOfPath(path: string | null | undefined): KnowledgeLane | null {
  if (!path) return null;
  const segment = path.split("/")[1];
  return isKnowledgeLane(segment) ? segment : null;
}

/**
 * The folder an upload should land in, relative to the collection's `sources/`
 * lane — the parent of the file currently open, or `null` for the lane's own
 * top level. A topic path never answers a folder: an upload is a source.
 */
export function uploadFolderOf(collection: string, selected: string | null): string | null {
  if (laneOfPath(selected) !== "sources") return null;
  const path = selected as string;
  const idx = path.lastIndexOf("/");
  if (idx === -1) return null;
  const parent = path.slice(0, idx);
  const root = lanePath(collection, "sources");
  return parent === root ? null : parent.slice(root.length + 1);
}
