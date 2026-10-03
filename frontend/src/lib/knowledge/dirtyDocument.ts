// frontend/src/lib/knowledge/dirtyDocument.ts
//
// The document open in the editor, and the one with unsaved edits (board
// 5.1.03). The editor sets both; the header drops Upload to secondary while a
// document is being edited (Save is the one primary then), and the tree marks
// the file with unsaved edits with an accent dot. Module-level values, since
// the page edits one document at a time; outside the editor they are null.
import { useSyncExternalStore } from "react";

function pathStore() {
  let current: string | null = null;
  const listeners = new Set<() => void>();
  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };
  return {
    set(path: string | null) {
      if (path === current) return;
      current = path;
      for (const l of listeners) l();
    },
    use: () => useSyncExternalStore(subscribe, () => current),
  };
}

const dirty = pathStore();
const editing = pathStore();

/** Mark the document whose draft differs from what is saved (null: none). */
export const setDirtyDocument = dirty.set;
/** The knowledge-root-relative path of the document with unsaved edits, or null. */
export const useDirtyDocument = dirty.use;
/** Mark the document open in the editor (null: none). */
export const setEditingDocument = editing.set;
/** The knowledge-root-relative path of the document open in the editor, or null. */
export const useEditingDocument = editing.use;
