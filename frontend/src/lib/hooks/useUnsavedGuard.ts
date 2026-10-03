// frontend/src/lib/hooks/useUnsavedGuard.ts — how a document editor registers unsaved edits (board 1.1.12).
// Spec web-ui "Guard unsaved edits when leaving a document editor".
// How a document editor tells the shell it holds edits that exist nowhere
// else. While `dirty`, the editor is registered with the guard provider
// (components/shell/UnsavedGuard.tsx), which stops every way out — a route
// change, a sidebar or palette jump, the title bar's arrows, closing or
// reloading the window — and asks once, in one dialog, naming the file and its
// owner. The editor contributes only what the dialog needs to say and to do:
// the file's name, whose it is, and a save that settles when the write has.
//
// Outside the provider (an editor rendered alone) registration is a no-op.
import { createContext, useContext, useEffect, useId, useRef } from "react";

/** @ui-only one registered editor with unsaved edits. */
export interface UnsavedEntry {
  /** The file being edited ("SKILL.md"). */
  file: string;
  /** Whose it is: the skill, collection or agent ("sentry-issue-triage"). */
  owner: string;
  /** Writes the edits; rejects when the write is refused. */
  save: () => Promise<unknown>;
}

/** @ui-only the provider's side of the registration. */
export interface UnsavedRegistry {
  register: (id: string, entry: UnsavedEntry) => () => void;
}

export const UnsavedGuardContext = createContext<UnsavedRegistry | null>(null);

/** @ui-only the editor's declaration. */
export interface UnsavedGuardOptions extends Omit<UnsavedEntry, "save"> {
  /** True while the draft differs from what is saved. */
  dirty: boolean;
  save: () => Promise<unknown>;
}

export function useUnsavedGuard({ dirty, file, owner, save }: UnsavedGuardOptions): void {
  const registry = useContext(UnsavedGuardContext);
  const id = useId();
  // The save closes over the latest draft; the registration must not be torn
  // down and rebuilt on every keystroke to keep it current.
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    if (!dirty || !registry) return;
    return registry.register(id, { file, owner, save: () => saveRef.current() });
  }, [dirty, file, owner, registry, id]);
}
