// frontend/src/lib/knowledge/crumbs.ts
//
// Where a document is, as the pane bar's crumbs: its collection (a link back to
// the collection's page), then each folder and the file, all in the mono face.
import type { CollectionOut } from "@/lib/api/knowledge";
import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";

export function crumbsOf(
  collection: CollectionOut,
  path: string,
): { label: string; to?: string; mono: boolean }[] {
  const parts = pathInCollection(path).split("/");
  return [
    { label: collection.name, to: collectionPath(collection.uid), mono: true },
    ...parts.map((p) => ({ label: p, mono: true })),
  ];
}
