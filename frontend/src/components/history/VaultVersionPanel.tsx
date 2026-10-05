// frontend/src/components/history/VaultVersionPanel.tsx
//
// The right half of a History tab: the chosen version — its short id, who
// wrote it and when — a switch between **Changes in this version** (against
// the version before it) and **Compare with current** (from this version to
// the file as it is now), **Restore this version…** on every version but the
// current one, and the diff of every file, each drawn by the one diff
// renderer (FileDiff) under its path, operation and line counts.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { VaultRestoreDialog } from "@/components/history/VaultRestoreDialog";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChangeItem, ChangeOp } from "@/lib/changePreview/changeCounts";
import { translateApiError } from "@/lib/api/errors";
import type { VaultDiffAgainst, VaultFileDiffOut, VaultVersionOut } from "@/lib/api/vault";
import { parseUnifiedDiff } from "@/lib/diff/unifiedDiff";
import { useVaultDiff } from "@/lib/hooks/useVaultHistory";
import { whenLabel } from "@/lib/knowledge/changes";
import { relPath, vaultWriterLabel } from "@/lib/vault/versionLabels";

interface Props {
  /** The history's path: a file, or a folder ending in `/`. */
  path: string;
  /** The path's versions, newest first. */
  versions: readonly VaultVersionOut[];
  /** The chosen version's position in that list. */
  index: number;
}

const STATUS_OP: Record<string, ChangeOp> = {
  added: "add",
  removed: "remove",
  modified: "modify",
};

function item(base: string, file: VaultFileDiffOut): ChangeItem {
  return {
    id: file.path,
    agentType: "coffer",
    path: relPath(base, file.path),
    op: STATUS_OP[file.status] ?? "modify",
    added: file.added,
    removed: file.removed,
    diff: parseUnifiedDiff(file.diff),
  };
}

export function VaultVersionPanel({ path, versions, index }: Props) {
  const { t, i18n } = useTranslation();
  const version = versions[index];
  const current = index === 0;
  const [against, setAgainst] = useState<VaultDiffAgainst>("previous");
  const [restoring, setRestoring] = useState(false);
  const shown: VaultDiffAgainst = current ? "previous" : against;
  const diff = useVaultDiff(path, version.version, shown);
  const items = useMemo(
    () => (diff.data?.files ?? []).map((f) => item(path, f)),
    [diff.data, path],
  );

  return (
    <section
      aria-label={t("history.versionLabel")}
      className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto"
    >
      <div className="flex shrink-0 flex-wrap items-center gap-2 p-3">
        <span className="font-mono text-xs font-medium text-text">
          {version.version.slice(0, 7)}
        </span>
        <span className="min-w-0 truncate text-xs text-text-muted">
          {vaultWriterLabel(t, version.display_writer)} ·{" "}
          {whenLabel(t, version.time, i18n.language)}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {current ? null : (
            <>
              <Segmented
                label={t("history.against.label")}
                value={against}
                onChange={setAgainst}
                options={[
                  { value: "previous", label: t("history.against.previous") },
                  { value: "current", label: t("history.against.current") },
                ]}
              />
              <Button variant="outline" size="sm" onClick={() => setRestoring(true)}>
                {t("history.restore")}
              </Button>
            </>
          )}
        </span>
      </div>
      <div className="flex flex-col gap-3.5 p-3 pt-1">
        {diff.error ? (
          <p role="alert" className="text-sm text-danger">
            {translateApiError(t, diff.error)}
          </p>
        ) : diff.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : items.length === 0 ? (
          <p className="text-sm text-text-muted">{t("history.noChanges")}</p>
        ) : (
          items.map((it) =>
            it.diff && it.diff.length > 0 ? (
              <FileDiff key={it.id} item={it} />
            ) : (
              <p key={it.id} className="text-xs text-text-muted">
                <span className="font-mono">{it.path}</span> · {t("history.noTextChange")}
              </p>
            ),
          )
        )}
      </div>
      <VaultRestoreDialog
        open={restoring}
        onOpenChange={setRestoring}
        path={path}
        target={version}
        newest={versions[0]}
      />
    </section>
  );
}
