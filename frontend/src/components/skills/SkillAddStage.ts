// src/components/skills/SkillAddStage.ts
// The Add skill dialog's one open stage: look at a source, choose among what it found, confirm — and cancel whatever stops being on screen.
//
// Spec skill-manager "Add skills from an archive": nothing is written until the
// user confirms, and the staging area is removed either way. So every stage
// this holds is cancelled when it is replaced, discarded or unmounted, and a
// stage that answers after the user moved on is cancelled the moment it lands.
import { useCallback, useEffect, useRef, useState } from "react";

import type { SkillOut, SkillStaging } from "@/lib/api/skills";
import {
  useCancelSkillStage,
  useConfirmSkillStage,
  useStageSkillSource,
  type SkillStageInput,
} from "@/lib/hooks/useSkills";
import { defaultSelection, isChoosable } from "./skillSourceHelpers";

export function useSkillAddStage() {
  const stageSource = useStageSkillSource();
  const confirmStage = useConfirmSkillStage();
  const cancelStage = useCancelSkillStage();

  const [stage, setStage] = useState<SkillStaging | null>(null);
  const [stageError, setStageError] = useState<unknown>(null);
  const [looking, setLooking] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmError, setConfirmError] = useState<unknown>(null);

  // The stage on screen and not yet confirmed.
  const openStage = useRef<string | null>(null);
  // Bumped whenever what is on screen changes, so a late answer is cancelled.
  const generation = useRef(0);
  const cancelRef = useRef(cancelStage.mutate);
  cancelRef.current = cancelStage.mutate;
  const stageRef = useRef(stageSource.mutateAsync);
  stageRef.current = stageSource.mutateAsync;

  const discard = useCallback(() => {
    generation.current += 1;
    const id = openStage.current;
    openStage.current = null;
    if (id) cancelRef.current(id);
    setStage(null);
    setStageError(null);
    setLooking(false);
    setSelected(new Set());
    setConfirmError(null);
  }, []);

  useEffect(() => discard, [discard]);

  const look = useCallback(
    async (input: SkillStageInput) => {
      discard();
      const mine = generation.current;
      setLooking(true);
      try {
        const staged = await stageRef.current(input);
        if (mine !== generation.current) {
          cancelRef.current(staged.staging_id);
          return;
        }
        openStage.current = staged.staging_id;
        setStage(staged);
        setSelected(defaultSelection(staged));
      } catch (error) {
        if (mine === generation.current) setStageError(error);
      } finally {
        if (mine === generation.current) setLooking(false);
      }
    },
    [discard],
  );

  const toggle = useCallback(
    (name: string) =>
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(name)) next.delete(name);
        else next.add(name);
        return next;
      }),
    [],
  );

  const chosen = stage ? stage.skills.filter(isChoosable).filter((s) => selected.has(s.name)) : [];

  /** Add the chosen skills, replacing the taken ones; resolves to what was added, or null when refused. */
  const confirm = async (): Promise<SkillOut[] | null> => {
    if (!stage || chosen.length === 0) return null;
    setConfirmError(null);
    try {
      const out = await confirmStage.mutateAsync({
        stagingId: stage.staging_id,
        skills: chosen.map((s) => s.name),
        replace: chosen.filter((s) => s.taken).map((s) => s.name),
      });
      // Confirmed: the daemon removed the stage, so there is nothing to cancel.
      openStage.current = null;
      return out.items;
    } catch (error) {
      // A refused confirm keeps the stage, so the user can choose again.
      setConfirmError(error);
      return null;
    }
  };

  return {
    stage,
    stageError,
    looking,
    selected,
    chosen,
    confirmError,
    confirming: confirmStage.isPending,
    look,
    discard,
    toggle,
    confirm,
  };
}
