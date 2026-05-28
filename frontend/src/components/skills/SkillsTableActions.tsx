// frontend/src/components/skills/SkillsTableActions.tsx
// Row + bulk actions for SkillsTable, kept out of SkillsTable.tsx so that file
// stays within its size budget. Per row: Verify (drift dialog scoped to the one
// skill) + Delete (styled confirm). Bulk: Verify the selected skills + Delete
// them all (styled confirm → parallel removes).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BadgeCheck, Trash2 } from "lucide-react";

import { SkillVerifyDialog } from "@/components/skills/SkillVerifyDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { skillsApi, type SkillOut } from "@/lib/api/skills";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

const DESTRUCTIVE =
  "text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive";

/** The two per-row icon+text actions: Verify (scoped) + Delete (confirm). The
 *  dialogs they open are rendered at the table level (hoisted out of the
 *  clickable row) so closing one can't fall through to the row's navigation —
 *  these buttons just signal the parent via onVerify/onDelete. */
export function SkillRowActions({
  skill,
  onVerify,
  onDelete,
  deleteDisabled,
}: {
  skill: SkillOut;
  onVerify: () => void;
  onDelete: () => void;
  deleteDisabled: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        size="sm"
        variant="ghost"
        className="text-muted-foreground hover:text-foreground"
        onClick={(e) => {
          e.stopPropagation();
          onVerify();
        }}
      >
        <BadgeCheck className="mr-1.5 size-3.5" /> {t("skills.verify")}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-muted-foreground hover:text-destructive"
        aria-label={t("skills.deleteAria", { name: skill.name })}
        disabled={deleteDisabled}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
      </Button>
    </div>
  );
}

/** Selection-bar actions: Verify the selected skills + Delete them all. */
export function SkillsBulkActions({ skills, onDone }: { skills: SkillOut[]; onDone: () => void }) {
  const { t } = useTranslation();
  // allSettled fan-out: one failed remove never aborts the rest; the summary
  // toast reports the outcome and we always close + clear (never stuck).
  const bulk = useBulkMutate({ invalidate: [["skills"]] });
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const deleteSelected = async () => {
    await bulk.run(skills, (s) => skillsApi.remove(s.name));
    setConfirmOpen(false);
    onDone();
  };

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setVerifyOpen(true)}>
        <BadgeCheck className="mr-1.5 size-3.5" /> {t("skills.verify")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        className={DESTRUCTIVE}
        disabled={bulk.isPending}
        onClick={() => setConfirmOpen(true)}
      >
        <Trash2 className="mr-1.5 size-3.5" /> {t("common.bulk.delete")}
      </Button>

      <SkillVerifyDialog
        open={verifyOpen}
        onOpenChange={setVerifyOpen}
        skillNames={skills.map((s) => s.name)}
      />

      <Dialog open={confirmOpen} onOpenChange={(o) => !o && setConfirmOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("skills.removeConfirmTitle", { name: skills.map((s) => s.name).join(", ") })}
            </DialogTitle>
            <DialogDescription>{t("skills.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={bulk.isPending} onClick={deleteSelected}>
              {bulk.isPending ? t("common.deleting") : t("common.bulk.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
