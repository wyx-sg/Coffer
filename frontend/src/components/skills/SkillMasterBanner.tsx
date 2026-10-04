// frontend/src/components/skills/SkillMasterBanner.tsx
// The banner of a skill whose master folder is gone (canvas 4.3.04): it names
// the folder, says reach and History are still here and when the last version
// is from, and carries the two ways forward — Restore from History (puts back
// the newest version of `skills/<name>/` that still had files, as a new
// version; spec vault-storage "Show, compare and restore any version of a
// vault file") and Delete skill… (the usual confirmation). Both are Coffer's
// own deterministic actions, so there is no hand-off. With no version to put
// back Restore is disabled and the body says so.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

import { SkillBannerFrame } from "@/components/skills/SkillBannerFrame";
import { SkillDeleteDialog } from "@/components/skills/SkillDeleteDialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillOut } from "@/lib/api/skills";
import type { VaultVersionOut } from "@/lib/api/vault";
import { useRestoreVaultVersion, useVaultHistory } from "@/lib/hooks/useVaultHistory";
import { clockTime, isToday, shortDay } from "@/lib/skills/format";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  skill: SkillOut;
  onDeleted: () => void;
}

/** The newest version that left files in the folder (the deletion itself
 *  removed every one it touched). */
function lastVersionWithFiles(versions: VaultVersionOut[]): VaultVersionOut | undefined {
  return versions.find((v) => v.paths.some((c) => c.status !== "removed"));
}

export function SkillMasterBanner({ skill, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const [deleting, setDeleting] = useState(false);
  const folder = `skills/${skill.name}/`;
  const history = useVaultHistory(folder);
  const restore = useRestoreVaultVersion();
  const lastGood = lastVersionWithFiles(history.data?.versions ?? []);
  const when = lastGood
    ? isToday(lastGood.time)
      ? t("skills.detail.todayAt", { time: clockTime(lastGood.time, i18n.language) })
      : shortDay(lastGood.time, i18n.language)
    : null;

  return (
    <>
      <SkillBannerFrame
        tone="error"
        testId="skill-banner-master"
        title={t("skills.banner.masterTitle")}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={!lastGood || restore.isPending}
              onClick={() =>
                lastGood &&
                restore.mutate(
                  { path: folder, version: lastGood.version, expected_fingerprint: null },
                  {
                    onSuccess: () =>
                      toast.success(t("skills.missing.restored", { name: skill.name })),
                    onError: (e) => toast.error(translateApiError(t, e)),
                  },
                )
              }
            >
              <RotateCcw aria-hidden /> {t("skills.missing.restoreButton")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={skill.builtin}
              onClick={() => setDeleting(true)}
            >
              {t("skills.missing.deleteButton")}
            </Button>
          </>
        }
      >
        {when
          ? t("skills.banner.masterBody", {
              path: abbreviateHomePath(skill.master_path),
              when,
            })
          : t("skills.banner.masterBodyNoHistory", { path: abbreviateHomePath(skill.master_path) })}
      </SkillBannerFrame>
      <SkillDeleteDialog
        skill={skill}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={onDeleted}
      />
    </>
  );
}
