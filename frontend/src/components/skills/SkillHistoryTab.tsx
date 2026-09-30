// frontend/src/components/skills/SkillHistoryTab.tsx
//
// A skill's History (spec vault-storage "Show, compare and restore any
// version of a vault file"; ADR
// every-vault-write-is-a-validated-commit-naming-its-writer — the skill's
// History tab is its first consumer): the versions of the skill's master
// folder `skills/<name>/`, newest first, each with who wrote it and when; for
// the chosen one, the diff of every file it changed; and Restore this version,
// which puts the whole folder back as a NEW version naming you. Coffer's own
// skill is rebuilt from the build at every start, so it has no history here.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { SkillVersionPanel } from "@/components/skills/SkillVersionPanel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { useVaultHistory } from "@/lib/hooks/useVaultHistory";
import { cn, formatDateTime } from "@/lib/utils";
import { vaultWriterLabel } from "@/lib/vault/writers";

export function SkillHistoryTab({ skill }: { skill: SkillOut }) {
  const { t } = useTranslation();
  // The vault folder the skill's master copy lives in.
  const folder = `skills/${skill.name}/`;
  const history = useVaultHistory(skill.builtin ? null : folder);
  const [chosen, setChosen] = useState<string | null>(null);

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
      <div role="alert" className="space-y-2 rounded-md border border-border-subtle p-4">
        <p className="text-sm font-semibold">{t("skills.history.failedTitle")}</p>
        <p className="text-sm text-text-muted">{translateApiError(t, history.error)}</p>
        <Button size="sm" variant="outline" onClick={() => void history.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
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
  const selected = versions.find((v) => v.version === chosen) ?? versions[0];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="shrink-0 space-y-1">
        <p className="text-xs text-text-subtle">
          {t("skills.history.count", { count: versions.length })}
        </p>
        <ul
          className="divide-y divide-border-subtle rounded-md border border-border-subtle"
          aria-label={t("skills.history.listLabel")}
        >
          {versions.map((v, i) => {
            const active = v.version === selected.version;
            return (
              <li key={v.version}>
                <button
                  type="button"
                  onClick={() => setChosen(v.version)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-left text-sm",
                    active ? "bg-surface-selected" : "hover:bg-surface-hover",
                  )}
                >
                  <span className="font-medium">{vaultWriterLabel(t, v.display_writer)}</span>
                  <span className="text-xs text-text-subtle">{formatDateTime(v.time)}</span>
                  {i === 0 ? (
                    <span className="rounded-sm bg-chip px-1.5 text-2xs text-text-muted">
                      {t("skills.history.current")}
                    </span>
                  ) : null}
                  <span className="w-full truncate text-xs text-text-muted">
                    {t("skills.history.filesChanged", { count: v.paths.length })}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <SkillVersionPanel
        folder={folder}
        version={selected}
        isCurrent={selected.version === versions[0].version}
      />
    </div>
  );
}
