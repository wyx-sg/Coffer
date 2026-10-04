// frontend/src/components/skills/SkillHistoryTab.tsx
//
// A skill's History (canvas 4.3.19, 4.3.20; spec vault-storage "Show, compare
// and restore any version of a vault file"; ADR
// every-vault-write-is-a-validated-commit-naming-its-writer): the same card as
// Files (VersionHistorySplit, the layout a knowledge document's History shares)
// — the versions of the skill's master folder `skills/<name>/` on the left under a "Versions" header, newest first, each with what it did and "who
// · when" (You, Coffer or Git), the newest wearing a Current chip; on the right
// what the chosen version changed and Restore this version…, which opens the
// 1060 review before the folder goes back (SkillRestoreDialog). Coffer's own
// skill is rebuilt from the build at every start, so it has no history here.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { VersionHistorySplit } from "@/components/history/VersionHistorySplit";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SkillRestoreDialog } from "@/components/skills/SkillRestoreDialog";
import { SkillVersionPanel } from "@/components/skills/SkillVersionPanel";
import { sourceIcon, versionTitle, versionWhen } from "@/components/skills/versionLabels";
import { Skeleton } from "@/components/ui/skeleton";
import type { SkillOut } from "@/lib/api/skills";
import { useVaultHistory } from "@/lib/hooks/useVaultHistory";
import { vaultWriterLabel } from "@/lib/vault/writers";

export function SkillHistoryTab({ skill }: { skill: SkillOut }) {
  const { t, i18n } = useTranslation();
  // The vault folder the skill's master copy lives in.
  const folder = `skills/${skill.name}/`;
  const history = useVaultHistory(skill.builtin ? null : folder);
  const [chosen, setChosen] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);

  if (skill.builtin) {
    return (
      <EmptyState
        icon={History}
        title={t("skills.history.builtinTitle")}
        description={t("skills.history.builtinBody")}
      />
    );
  }
  if (history.isPending) {
    return (
      <div className="space-y-2" aria-busy>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    );
  }
  if (history.error) {
    return (
      <LoadErrorRow
        title={t("skills.history.failedTitle")}
        error={history.error}
        onRetry={() => void history.refetch()}
      />
    );
  }

  const versions = history.data.versions;
  if (versions.length === 0) {
    return (
      <EmptyState
        icon={History}
        title={t("skills.history.title")}
        description={t("skills.history.none")}
      />
    );
  }
  const index = Math.max(
    0,
    versions.findIndex((v) => v.version === chosen),
  );

  return (
    <VersionHistorySplit
      storageKey="skill-history"
      versions={versions}
      getKey={(v) => v.version}
      selectedIndex={index}
      onSelect={(i) => setChosen(versions[i].version)}
      listLabel={t("skills.history.listLabel")}
      currentLabel={t("skills.history.current")}
      dividerLabel={t("splitView.resizeList")}
      renderRow={(v) => {
        const Icon = sourceIcon(v.display_writer);
        return {
          icon: (
            <span className="inline-flex size-[26px] shrink-0 items-center justify-center rounded-full bg-chip text-text-muted">
              <Icon className="size-3.5" aria-hidden />
            </span>
          ),
          title: versionTitle(t, v, folder, versions, i18n.language),
          subline: `${vaultWriterLabel(t, v.display_writer)} · ${versionWhen(t, v, i18n.language)}`,
        };
      }}
      detail={
        <SkillVersionPanel
          key={versions[index].version}
          folder={folder}
          versions={versions}
          index={index}
          onRestore={() => setRestoring(true)}
        />
      }
    >
      {restoring ? (
        <SkillRestoreDialog
          skill={skill}
          versions={versions}
          target={versions[index]}
          folder={folder}
          open
          onOpenChange={(open) => !open && setRestoring(false)}
        />
      ) : null}
    </VersionHistorySplit>
  );
}
