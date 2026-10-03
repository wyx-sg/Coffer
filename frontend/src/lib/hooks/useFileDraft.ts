// frontend/src/lib/hooks/useFileDraft.ts — specs agent-registry / skill-manager / knowledge.
// Draft state for an in-app file editor, shared by the agent config-file pane,
// the skill file pane, the knowledge document pane and the memory editor. Each edits a file that ALSO lives on the
// user's disk and is edited there, so each needs the same three things: a draft
// separate from the loaded content, an explicit save, and a conflict the user
// can act on rather than a silent overwrite.
//
// The conditional-write contract is the daemon's, not this hook's: a save
// carries the fingerprint the read returned, and the daemon answers 409 when
// the bytes on disk no longer match it. The hook's job is to keep the draft
// intact when that happens — losing what the user typed is the one outcome
// worse than the conflict itself.
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";
import { useUnsavedGuard } from "@/lib/hooks/useUnsavedGuard";

/** @ui-only hook options; never crosses the wire. */
export interface FileDraftOptions {
  /** Content as last loaded from the daemon; `undefined` while loading. */
  loaded: string | undefined;
  /** Fingerprint from the same read. Sent back to make the save conditional. */
  fingerprint: string | undefined;
  /** Issues the save. Resolves with the fingerprint the write returned, when
   *  the endpoint reports one — that lets a second save in the same session
   *  succeed without a round-trip through the read. */
  save: (content: string, expectedFingerprint: string | null) => Promise<string | undefined>;
  /** Re-reads the file from the daemon (the answer to a conflict). */
  reload: () => Promise<unknown>;
  /** What the unsaved-edits guard names when the user tries to leave with a
   *  dirty draft: the file ("SKILL.md") and whose it is ("sentry-issue-triage"). */
  guard: { file: string; owner: string };
}

/** True when the error is the daemon refusing a save because the file changed
 *  on disk. Each file kind carries its own code for it. */
function isStaleConflict(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === "CONFIG_FILE_STALE" ||
      error.code === "SKILL_FILE_STALE" ||
      error.code === "KNOWLEDGE_FILE_CONFLICT" ||
      error.code === "MEMORY_NOTE_CONFLICT")
  );
}

export function useFileDraft(opts: FileDraftOptions) {
  const [draft, setDraft] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  // Tracks the fingerprint to send with the next save. Starts as the one the
  // read returned and advances on every successful write, so the editor does
  // not 409 against its own previous save.
  const [current, setCurrent] = useState<string | undefined>(opts.fingerprint);
  const loadedRef = useRef(opts.loaded);
  const fileId = `${opts.guard.owner}/${opts.guard.file}`;
  const fileIdRef = useRef(fileId);

  // A different file (or a reload) replaced the content underneath us. Drop the
  // draft and leave edit mode: the draft belonged to the old bytes, and keeping
  // it would silently re-apply it to a different file — two files with equal
  // content included, so the file's identity counts as well as its bytes.
  useEffect(() => {
    if (opts.loaded !== loadedRef.current || fileId !== fileIdRef.current) {
      loadedRef.current = opts.loaded;
      fileIdRef.current = fileId;
      setDraft(null);
      setEditing(false);
    }
    setCurrent(opts.fingerprint);
  }, [opts.loaded, opts.fingerprint, fileId]);

  const baseline = opts.loaded ?? "";
  const value = draft ?? baseline;
  const dirty = draft !== null && draft !== baseline;

  const mutation = useMutation({
    mutationFn: () => opts.save(value, current ?? null),
    onSuccess: (next) => {
      if (next) setCurrent(next);
      // The draft IS now the file, so fold it into the baseline by clearing it
      // and leaving edit mode. A reload is still issued so metadata (size,
      // modified time, the rendered view) catches up.
      setDraft(null);
      setEditing(false);
      void opts.reload();
    },
  });

  useUnsavedGuard({
    dirty,
    file: opts.guard.file,
    owner: opts.guard.owner,
    save: () => mutation.mutateAsync(),
  });

  return {
    value,
    dirty,
    editing,
    setDraft,
    startEditing: () => setEditing(true),
    /** Leave edit mode, discarding the draft. */
    cancel: () => {
      setDraft(null);
      setEditing(false);
      mutation.reset();
    },
    save: () => mutation.mutate(),
    /** The same save as a promise, for "Save and leave": rejects when refused. */
    saveAsync: () => mutation.mutateAsync(),
    saving: mutation.isPending,
    error: mutation.error,
    conflict: isStaleConflict(mutation.error),
    /** Answer to a conflict: take the daemon's copy, losing the draft. The
     *  caller confirms with the user first — this is destructive to their
     *  unsaved text. */
    discardAndReload: async () => {
      setDraft(null);
      setEditing(false);
      mutation.reset();
      await opts.reload();
    },
  };
}
