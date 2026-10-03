// frontend/src/components/skills/SkillHistoryTab.tsx
//
// A skill's History (canvas 4.3.19, 4.3.20; spec vault-storage "Show, compare
// and restore any version of a vault file"; ADR
// every-vault-write-is-a-validated-commit-naming-its-writer): the same card as
// Files — the versions of the skill's master folder `skills/<name>/` on the
// left under a "Versions" header, newest first, each with what it did and "who
// · when" (You, Coffer or Git), the newest wearing a Current chip; on the right
// what the chosen version changed and Restore this version…, which opens the
// 1060 review before the folder goes back (SkillRestoreDialog). Coffer's own
// skill is rebuilt from the build at every start, so it has no history here.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { useFillToBottom } from "@/components/filePane";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SplitView } from "@/components/SplitView";
import { SkillRestoreDialog } from "@/components/skills/SkillRestoreDialog";
import { SkillVersionPanel } from "@/components/skills/SkillVersionPanel";
import { sourceIcon, versionTitle, versionWhen } from "@/components/skills/versionLabels";
import { Skeleton } from "@/components/ui/skeleton";
import type { SkillOut } from "@/lib/api/skills";
import { useVaultHistory } from "@/lib/hooks/useVaultHistory";
import { cn } from "@/lib/utils";
import { vaultWriterLabel } from "@/lib/vault/writers";

export function SkillHistoryTab({ skill }: { skill: SkillOut }) {
  const { t, i18n } = useTranslation();
  // The vault folder the skill's master copy lives in.
  const folder = `skills/${skill.name}/`;
  const history = useVaultHistory(skill.builtin ? null : folder);
  const [chosen, setChosen] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);
  const fill = useFillToBottom();

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

  const list = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-border-subtle px-3">
        <span className="text-sm font-semibold text-text">{t("skills.history.listLabel")}</span>
        <span className="ml-auto text-xs text-text-subtle">{versions.length}</span>
      </div>
      <ul
        className="flex min-h-0 flex-1 flex-col gap-px overflow-auto p-1"
        aria-label={t("skills.history.listLabel")}
      >
        {versions.map((v, i) => {
          const active = i === index;
          const Icon = sourceIcon(v.display_writer);
          return (
            <li key={v.version}>
              <button
                type="button"
                onClick={() => setChosen(v.version)}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-item p-2 text-left",
                  active ? "bg-surface-selected" : "hover:bg-surface-hover",
                )}
              >
                <span className="inline-flex size-[26px] shrink-0 items-center justify-center rounded-full bg-chip text-text-muted">
                  <Icon className="size-3.5" aria-hidden />
                </span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "min-w-0 truncate text-sm text-text",
                        active ? "font-label" : "font-medium",
                      )}
                    >
                      {versionTitle(t, v, folder, versions, i18n.language)}
                    </span>
                    {i === 0 ? (
                      <span className="inline-flex h-[18px] shrink-0 items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
                        {t("skills.history.current")}
                      </span>
                    ) : null}
                  </span>
                  <span className="truncate text-xs text-text-muted">
                    {vaultWriterLabel(t, v.display_writer)} · {versionWhen(t, v, i18n.language)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div
      ref={fill.ref}
      style={fill.style}
      className="flex min-h-0 overflow-hidden rounded-xl border border-border-subtle"
    >
      <SplitView
        storageKey="skill-history"
        label={t("splitView.resizeList")}
        defaultListWidth={250}
        className="min-h-0 flex-1"
        list={list}
        detail={
          <SkillVersionPanel
            key={versions[index].version}
            folder={folder}
            versions={versions}
            index={index}
            onRestore={() => setRestoring(true)}
          />
        }
      />
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
    </div>
  );
}
