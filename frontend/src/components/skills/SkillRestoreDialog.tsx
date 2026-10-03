// frontend/src/components/skills/SkillRestoreDialog.tsx
// "Restore the version of Sep 27" (canvas 4.3.20, Foundations 0.7.03): the 1060
// change preview before a whole skill folder goes back to an older version — what
// will happen (Coffer writes the old files as a NEW version on top of today's, so
// nothing in History is removed; every agent sees them at once through its link),
// the files that differ with their diffs, and "Restore N files". The diffs are the
// newer versions' own diffs read the other way round, so what is shown is exactly
// what the restore undoes. A refusal stays here and the primary becomes Retry.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { SkillChangeDialog } from "@/components/skills/SkillChangeDialog";
import { useHolderSummaries } from "@/components/skills/skillSummaries";
import { reverseDiffLines } from "@/components/skills/reverseDiff";
import { relPath, versionTitle } from "@/components/skills/versionLabels";
import { useVersionDiffs, type DiffRequest } from "@/components/skills/useVersionDiffs";
import { parseUnifiedDiff } from "@/components/skills/skillSourceHelpers";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { ChangeItem, ChangeOp } from "@/lib/changePreview/changeCounts";
import { translateApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import type { VaultVersionOut } from "@/lib/api/vault";
import { useRestoreVaultVersion } from "@/lib/hooks/useVaultHistory";

interface Props {
  skill: SkillOut;
  /** The folder's versions, newest first. */
  versions: readonly VaultVersionOut[];
  /** The version to put back. */
  target: VaultVersionOut;
  folder: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** The net operation restoring does to a path, from the statuses of the newer versions that touched it (oldest first). */
function netOp(statuses: readonly string[]): ChangeOp | null {
  const oldest = statuses[0];
  const newest = statuses[statuses.length - 1];
  if (oldest === "added" && newest === "removed") return null;
  if (oldest === "added") return "remove";
  if (newest === "removed") return "add";
  return "modify";
}

export function SkillRestoreDialog({ skill, versions, target, folder, open, onOpenChange }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const restore = useRestoreVaultVersion();
  const when = new Date(target.time).toLocaleDateString(i18n.language, {
    day: "numeric",
    month: "short",
  });
  const summaries = useHolderSummaries(
    skill,
    t("skills.restore.coffer", { date: when }),
    t("skills.restore.agent"),
  );

  // The versions newer than the target, newest first — each file they touched.
  const newer = useMemo(() => {
    const at = versions.findIndex((v) => v.version === target.version);
    return at < 0 ? [] : versions.slice(0, at);
  }, [versions, target.version]);
  const requests = useMemo(() => {
    const out: (DiffRequest & { status: string })[] = [];
    for (const v of newer)
      for (const p of v.paths) out.push({ path: p.path, version: v.version, status: p.status });
    return out;
  }, [newer]);
  const { pending, error: readError, diffs } = useVersionDiffs(requests);

  const items = useMemo<ChangeItem[] | null>(() => {
    if (pending) return null;
    const byPath = new Map<string, { status: string; index: number }[]>();
    requests.forEach((r, index) => {
      byPath.set(r.path, [...(byPath.get(r.path) ?? []), { status: r.status, index }]);
    });
    const out: ChangeItem[] = [];
    for (const [path, entries] of byPath) {
      // `requests` runs newest first; the net operation reads oldest first.
      const op = netOp([...entries].reverse().map((e) => e.status));
      if (!op) continue;
      let added = 0;
      let removed = 0;
      const lines = entries.flatMap(({ index }) => {
        const d = diffs[index];
        if (!d) return [];
        // Undoing a version swaps what it added and removed.
        added += d.removed;
        removed += d.added;
        return reverseDiffLines(parseUnifiedDiff(d.diff));
      });
      out.push({
        id: path,
        agentType: "coffer",
        agentName: `Coffer · ${skill.name}`,
        path: relPath(folder, path),
        op,
        added,
        removed,
        diff: lines,
      });
    }
    return out;
  }, [pending, requests, diffs, folder, skill.name]);

  const short = target.version.slice(0, 7);
  const confirm = () =>
    restore.mutate(
      { path: folder, version: target.version, expected_fingerprint: null },
      {
        onSuccess: () => {
          toast.success(t("skills.restore.toast", { date: when }));
          onOpenChange(false);
        },
      },
    );

  const empty = items !== null && items.length === 0 && !readError;
  return (
    <SkillChangeDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("skills.restore.title", { date: when })}
      subtitle={`${skill.name} · ${short} · ${versionTitle(t, target, folder, versions, i18n.language)}`}
      items={items ?? (readError ? [] : null)}
      summaries={summaries}
      notice={
        readError ? (
          <p role="alert" className="text-sm text-danger">
            {translateApiError(t, readError)}
          </p>
        ) : empty ? (
          <p className="text-sm text-text-muted">{t("skills.restore.same")}</p>
        ) : undefined
      }
      loadingLabel={t("skills.restore.loading")}
      note={t("skills.restore.note")}
      confirmLabel={t("skills.restore.confirm", { count: items?.length ?? 0 })}
      onConfirm={confirm}
      pending={restore.isPending}
      closeOnly={empty}
      error={
        restore.error ? (
          <DialogErrorBanner
            title={t("skills.restore.failed")}
            message={translateApiError(t, restore.error)}
          />
        ) : null
      }
    />
  );
}
