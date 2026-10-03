// frontend/src/components/skills/SkillBulkDelete.tsx
// Delete every selected skill behind one confirmation — the selection bar's
// Delete and the selection pane's "Delete 3 skills…". The deletes fan out
// through useBulkMutate: one refused delete (an agent's copy that is no longer
// Coffer's link) never stops the others, and one summary toast says how many
// landed. The selection clears once the batch has settled.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SkillOut } from "@/lib/api/skills";
import { useBulkRemoveSkills } from "@/lib/hooks/useSkills";
import { joinNames } from "@/lib/skills/names";

interface Props {
  skills: SkillOut[];
  onDone: () => void;
  /** The trigger's label: "Delete" in the bar, "Delete 3 skills…" in the pane. */
  label: string;
}

export function SkillBulkDelete({ skills, onDone, label }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const bulk = useBulkRemoveSkills();

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Trash2 aria-hidden /> {label}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={t("skills.bulk.deleteTitle", { count: skills.length })}
        description={t("skills.bulk.deleteBody", {
          names: joinNames(
            skills.map((s) => s.name),
            i18n.language,
          ),
        })}
        confirmLabel={t("skills.bulk.deleteConfirm", { count: skills.length })}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(skills);
          onDone();
        }}
      />
    </>
  );
}
