// frontend/src/components/skills/SkillVersionPanel.tsx
// The right half of a skill's History (canvas 4.3.19, 4.3.20): for the chosen
// version, what it was compared with — From (the version before it) and To (this
// one), with a sentence on who made it and, at its right, Restore this version…
// (the newest version is current and offers none) — then, for every file the
// version touched, its name, operation, line counts and diff. Comparing two
// other versions is not offered yet: the daemon reads what one version did to
// one file, not a range.
import { ArrowRight } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { versionNote, versionWhen } from "@/components/skills/versionLabels";
import { diffItem, useVersionDiffs } from "@/components/skills/useVersionDiffs";
import { relPath } from "@/components/skills/versionLabels";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import type { ChangeItem } from "@/lib/changePreview/changeCounts";
import type { VaultVersionOut } from "@/lib/api/vault";
import { vaultWriterLabel } from "@/lib/vault/writers";

interface Props {
  folder: string;
  /** The folder's versions, newest first. */
  versions: readonly VaultVersionOut[];
  /** The chosen version's position in that list. */
  index: number;
  onRestore: () => void;
}

function Pick({ label, version }: { label: string; version: VaultVersionOut | null }) {
  const { t, i18n } = useTranslation();
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <span className="text-2xs text-text-muted">{label}</span>
      <div className="flex h-[30px] min-w-0 items-center gap-2 rounded-item border border-border bg-surface-raised px-2.5">
        {version ? (
          <>
            <span className="font-mono text-xs font-medium text-text">
              {version.version.slice(0, 7)}
            </span>
            <span className="min-w-0 truncate text-xs text-text-muted">
              {versionWhen(t, version, i18n.language)} ·{" "}
              {vaultWriterLabel(t, version.display_writer)}
            </span>
          </>
        ) : (
          <span className="text-xs text-text-muted">{t("skills.history.start")}</span>
        )}
      </div>
    </div>
  );
}

export function SkillVersionPanel({ folder, versions, index, onRestore }: Props) {
  const { t, i18n } = useTranslation();
  const version = versions[index];
  const previous = versions[index + 1] ?? null;
  const current = index === 0;
  const requests = useMemo(
    () => version.paths.map((p) => ({ path: p.path, version: version.version })),
    [version],
  );
  const { pending, error, diffs } = useVersionDiffs(requests);
  const items = useMemo<ChangeItem[]>(
    () =>
      version.paths.flatMap((p, i) => {
        const d = diffs[i];
        return d ? [{ ...diffItem(p.path, relPath(folder, p.path), p.status, d) }] : [];
      }),
    [version, diffs, folder],
  );
  const agentName = version.display_writer.startsWith("agent:")
    ? agentTypeLabel(version.display_writer.slice(6).replace(/-/g, "_"))
    : "";

  return (
    <section
      aria-label={t("skills.history.versionLabel")}
      className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto"
    >
      <div className="flex shrink-0 flex-col gap-2.5 p-3">
        <div className="flex items-end gap-2">
          <Pick label={t("skills.history.from")} version={previous} />
          <span className="flex h-[30px] items-center text-text-subtle">
            <ArrowRight className="size-3.5" aria-hidden />
          </span>
          <Pick label={t("skills.history.to")} version={version} />
        </div>
        <div className="flex items-center gap-2">
          <span className="min-w-0 text-xs text-text-muted">
            {versionNote(t, version, folder, versions, current, i18n.language, agentName)}
          </span>
          {current ? null : (
            <Button variant="outline" size="sm" className="ml-auto shrink-0" onClick={onRestore}>
              {t("skills.history.restore")}
            </Button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-3.5 p-3 pt-1">
        {version.paths.length === 0 ? (
          <p className="text-sm text-text-muted">{t("skills.history.noFiles")}</p>
        ) : error ? (
          <p role="alert" className="text-sm text-danger">
            {translateApiError(t, error)}
          </p>
        ) : pending ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          items.map((item) =>
            item.diff && item.diff.length > 0 ? (
              <FileDiff key={item.id} item={item} />
            ) : (
              <p key={item.id} className="text-xs text-text-muted">
                <span className="font-mono">{item.path}</span> · {t("skills.history.noTextChange")}
              </p>
            ),
          )
        )}
      </div>
    </section>
  );
}
