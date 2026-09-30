// src/components/skills/SkillUpdateStage.ts
// The update dialog's staged preview: staged when the dialog opens, cancelled on every way out that does not apply it.
//
// Spec skill-manager "Update a Git-imported skill from its source": a preview
// applies nothing, and closing it leaves the folder and the pin as they were.
import { useCallback, useEffect, useRef, useState } from "react";

import type { SkillUpdatePreview } from "@/lib/api/skills";
import { useCancelSkillStage, usePreviewSkillUpdate } from "@/lib/hooks/useSkills";

export function useSkillUpdateStage(uid: string, open: boolean) {
  const previewUpdate = usePreviewSkillUpdate();
  const cancelStage = useCancelSkillStage();
  const [preview, setPreview] = useState<SkillUpdatePreview | null>(null);
  const [error, setError] = useState<unknown>(null);

  const openStage = useRef<string | null>(null);
  const generation = useRef(0);
  const cancelRef = useRef(cancelStage.mutate);
  cancelRef.current = cancelStage.mutate;
  const previewRef = useRef(previewUpdate.mutateAsync);
  previewRef.current = previewUpdate.mutateAsync;

  /** Cancel the staged preview (Not now, Keep my edits, closing). */
  const discard = useCallback(() => {
    generation.current += 1;
    const id = openStage.current;
    openStage.current = null;
    if (id) cancelRef.current(id);
  }, []);

  /** The preview was applied: the daemon consumed its stage. */
  const consumed = useCallback(() => {
    openStage.current = null;
  }, []);

  useEffect(() => {
    if (!open) {
      discard();
      return;
    }
    const mine = ++generation.current;
    setPreview(null);
    setError(null);
    previewRef.current(uid).then(
      (staged) => {
        if (mine !== generation.current) {
          cancelRef.current(staged.staging_id);
          return;
        }
        openStage.current = staged.staging_id;
        setPreview(staged);
      },
      (reason: unknown) => {
        if (mine === generation.current) setError(reason);
      },
    );
  }, [open, uid, discard]);

  useEffect(() => discard, [discard]);

  return { preview, error, discard, consumed };
}
