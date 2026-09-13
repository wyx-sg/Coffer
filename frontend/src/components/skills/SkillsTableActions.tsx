// frontend/src/components/skills/SkillsTableActions.tsx
// Row + bulk actions for SkillsTable, kept out of SkillsTable.tsx so that file
// stays within its size budget. Per row: the same three-state ScopeControl the
// detail page carries (the skill's own reach: Disabled / Every agent / Selected
// agents) + Delete (styled confirm). Bulk: that same reach choice applied to
// the whole selection + Delete them all.
//
// There is no Verify/Repair here any more. The drift report still exists on the
// CLI and REST — it is a real maintenance capability — but the button was never
// used: the live audit log holds zero `skill_drift_remediated` events across
// its whole history, so the surface was cost without a reader.
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { skillsApi, type SkillOut } from "@/lib/api/skills";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

/** Per-row reach control for the skill itself: enable/disable is only one of
 *  its three states, so the list shows the same control the detail page does
 *  rather than a Switch that cannot express "active for these agents".
 *
 *  `skill.scope` comes from the list payload, so the control never fires its
 *  own per-resource GET — a list of N skills still costs one request.
 *
 *  The wrapper stops propagation so neither a segment click nor a checkbox
 *  inside the popover (a React portal still bubbles through the React tree)
 *  triggers the row's navigate-to-detail click. */
export function SkillStatusCell({ skill }: { skill: SkillOut }) {
  return (
    <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
      <ScopeControl kind="skill" name={skill.name} enabled={skill.enabled} scope={skill.scope} />
    </div>
  );
}

/** The per-row action: Delete (confirm). The dialog it opens is rendered at the
 *  table level (hoisted out of the clickable row) so closing it can't fall
 *  through to the row's navigation — this button just signals the parent via
 *  onDelete. */
export function SkillRowActions({
  skill,
  onDelete,
  deleteDisabled,
}: {
  skill: SkillOut;
  onDelete: () => void;
  deleteDisabled: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-end gap-2">
      <RowDeleteButton
        ariaLabel={t("skills.deleteAria", { name: skill.name })}
        disabled={deleteDisabled}
        onDelete={onDelete}
      />
    </div>
  );
}

/** Selection-bar actions: the selection's reach + Delete them all. */
export function SkillsBulkActions({ skills, onDone }: { skills: SkillOut[]; onDone: () => void }) {
  const { t } = useTranslation();
  // allSettled fan-out: one failed remove never aborts the rest; the summary
  // toast reports the outcome and we always close + clear (never stuck).
  const bulk = useBulkMutate({ invalidate: [["skills"]] });

  return (
    <>
      <BulkReachActions
        rows={skills.map((s) => ({ kind: "skill", name: s.name }))}
        invalidate={[["skills"]]}
        onDone={onDone}
      />
      <BulkDeleteButton
        title={t("skills.removeConfirmTitle", { name: skills.map((s) => s.name).join(", ") })}
        description={t("skills.removeConfirmBody")}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(skills, (s) => skillsApi.remove(s.name));
          onDone();
        }}
      />
    </>
  );
}
