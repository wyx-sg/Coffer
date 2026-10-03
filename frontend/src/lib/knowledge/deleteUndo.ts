// frontend/src/lib/knowledge/deleteUndo.ts
//
// Undo for a delete (boards 5.1.02, 5.1.14; layout principle 14 "confirm or
// undo"). Deleting a document or a collection is one change in the vault's
// history, and Recent changes can restore it — so the delete runs at once and
// its toast carries Undo instead of a confirmation first. Undo is that same
// Restore: it finds the change the delete just recorded (the newest `delete`
// of the document, or `remove` of the collection) and restores it.
import { listChanges, restoreDeleted } from "@/lib/api/knowledge";
import type { ChangeOut } from "@/lib/api/knowledgeTypes";

export type DeletedTarget = { document: string } | { collection: string };

/** The change that recorded `target`'s delete, among the newest few. */
function isDeletionOf(change: ChangeOut, target: DeletedTarget): boolean {
  if ("document" in target) {
    return (
      change.operation === "delete" && change.documents.some((d) => d.path === target.document)
    );
  }
  return change.operation === "remove" && change.collections.includes(target.collection);
}

/** Restore what was just deleted. Rejects when the delete is not among the
 *  newest changes or the restore is refused (the name is taken again). */
export async function undoDelete(target: DeletedTarget): Promise<ChangeOut> {
  const { changes } = await listChanges({ limit: 20 });
  const change = changes.find((c) => isDeletionOf(c, target));
  if (!change) throw new Error("The delete is no longer in Recent changes.");
  return restoreDeleted(change.version);
}
