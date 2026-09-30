// frontend/src/components/skills/SkillMissingMaster.tsx
// The Files tab of a skill whose master folder is gone (canvas 4.3.27): the
// two ways forward, chosen and then confirmed — Restore it from History, or
// Remove the skill (its row and settings; the confirmation is the usual
// delete). Restore puts back the newest version of `skills/<name>/` that still
// had files, as a new version (spec vault-storage "Show, compare and restore
// any version of a vault file"); with no such version it can't be chosen.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, Trash2 } from "lucide-react";

import { SkillChoiceCards } from "@/components/skills/SkillChoiceCards";
import { SkillDeleteDialog } from "@/components/skills/SkillDeleteDialog";
import { Button } from "@/components/ui/button";
import type { SkillOut } from "@/lib/api/skills";
import type { VaultVersionOut } from "@/lib/api/vault";
import { useRestoreVaultVersion, useVaultHistory } from "@/lib/hooks/useVaultHistory";

type Way = "restore" | "remove";

interface Props {
  skill: SkillOut;
  onDeleted: () => void;
}

export function SkillMissingMaster({ skill, onDeleted }: Props) {
  const { t } = useTranslation();
  const [way, setWay] = useState<Way | null>(null);
  const [deleting, setDeleting] = useState(false);
  const folder = `skills/${skill.name}/`;
  const history = useVaultHistory(folder);
  const restore = useRestoreVaultVersion();
  const lastGood = lastVersionWithFiles(history.data?.versions ?? []);

  return (
    <section className="flex flex-col gap-3" aria-label={t("skills.missing.label")}>
      <SkillChoiceCards<Way>
        label={t("skills.missing.label")}
        value={way}
        onChange={setWay}
        choices={[
          {
            value: "restore",
            title: t("skills.missing.restore"),
            help: lastGood
              ? t("skills.missing.restoreHelp", { when: new Date(lastGood.time).toLocaleString() })
              : t("skills.missing.restoreUnavailable"),
            disabled: !lastGood,
          },
          {
            value: "remove",
            title: t("skills.missing.remove"),
            help: t("skills.missing.removeHelp", { name: skill.name }),
            disabled: skill.builtin,
          },
        ]}
      />
      <div className="flex justify-end">
        {way === "remove" ? (
          <Button variant="destructive" onClick={() => setDeleting(true)}>
            <Trash2 aria-hidden /> {t("skills.missing.removeConfirm", { name: skill.name })}
          </Button>
        ) : (
          <Button
            disabled={way !== "restore" || !lastGood || restore.isPending}
            onClick={() =>
              lastGood &&
              restore.mutate({
                path: folder,
                version: lastGood.version,
                expected_fingerprint: null,
              })
            }
          >
            <RotateCcw aria-hidden /> {t("skills.missing.restoreConfirm", { name: skill.name })}
          </Button>
        )}
      </div>
      <SkillDeleteDialog
        skill={skill}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={onDeleted}
      />
    </section>
  );
}

/** The newest version that left files in the folder (the deletion itself
 *  removed every one it touched). */
function lastVersionWithFiles(versions: VaultVersionOut[]): VaultVersionOut | undefined {
  return versions.find((v) => v.paths.some((c) => c.status !== "removed"));
}
