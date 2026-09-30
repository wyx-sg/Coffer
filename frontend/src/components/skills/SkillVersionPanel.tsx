// frontend/src/components/skills/SkillVersionPanel.tsx
//
// One version of a skill folder on its History tab: who and when, the diff of
// every file it changed, and Restore this version — confirmed first, because
// it puts the whole folder back (a file the version did not have is removed),
// and written as a NEW version naming you, so the restore can itself be undone
// the same way. A refusal (a file edited on disk since) is shown in the dialog,
// which stays open.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { VaultPathChangeOut, VaultVersionOut } from "@/lib/api/vault";
import { parseUnifiedDiff } from "@/lib/knowledge/unifiedDiff";
import { useRestoreVaultVersion, useVaultDiff } from "@/lib/hooks/useVaultHistory";
import { formatDateTime } from "@/lib/utils";
import { vaultWriterLabel } from "@/lib/vault/writers";

interface Props {
  /** The skill's vault folder, ending in `/`. */
  folder: string;
  version: VaultVersionOut;
  isCurrent: boolean;
}

export function SkillVersionPanel({ folder, version, isCurrent }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const restore = useRestoreVaultVersion();
  const [confirming, setConfirming] = useState(false);
  const short = version.version.slice(0, 7);

  const confirm = () =>
    restore
      .mutateAsync({ path: folder, version: version.version, expected_fingerprint: null })
      .then((done) =>
        toast.success(
          done.version
            ? t("skills.history.restored", { version: short })
            : t("skills.history.unchanged"),
        ),
      );

  return (
    <section className="space-y-3" aria-label={t("skills.history.versionLabel")}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm">
          <span className="font-semibold">{formatDateTime(version.time)}</span>
          <span className="text-text-subtle"> · {vaultWriterLabel(t, version.display_writer)}</span>
          {version.restored_from ? (
            <span className="text-text-subtle">
              {" "}
              · {t("skills.history.restoredFrom", { version: version.restored_from.slice(0, 7) })}
            </span>
          ) : null}
        </p>
        {!isCurrent ? (
          <Button
            className="ml-auto"
            variant="outline"
            size="sm"
            disabled={restore.isPending}
            onClick={() => setConfirming(true)}
          >
            <RotateCcw aria-hidden /> {t("skills.history.restore")}
          </Button>
        ) : null}
      </div>
      {version.paths.length === 0 ? (
        <p className="text-sm text-text-subtle">{t("skills.history.noFiles")}</p>
      ) : (
        version.paths.map((change) => (
          <SkillVersionFileDiff
            key={change.path}
            folder={folder}
            change={change}
            version={version.version}
          />
        ))
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("skills.history.confirmTitle")}
        description={t("skills.history.confirmBody", { version: short })}
        confirmLabel={t("skills.history.restore")}
        variant="default"
        pending={restore.isPending}
        onConfirm={confirm}
      />
    </section>
  );
}

function SkillVersionFileDiff({
  folder,
  change,
  version,
}: {
  folder: string;
  change: VaultPathChangeOut;
  version: string;
}) {
  const { t } = useTranslation();
  const diff = useVaultDiff(change.path, version);
  const name = change.path.startsWith(folder) ? change.path.slice(folder.length) : change.path;
  return (
    <div className="space-y-1" data-testid={`skill-version-file-${name}`}>
      <p className="text-xs">
        <span className="font-mono">{name}</span>
        <span className="text-text-subtle">
          {" "}
          · {t(`skills.history.status.${change.status}`, { defaultValue: change.status })} · +
          {change.added} −{change.removed}
        </span>
      </p>
      {diff.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : diff.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, diff.error)}
        </p>
      ) : diff.data.diff ? (
        <KnowledgeDiff rows={parseUnifiedDiff(diff.data.diff)} />
      ) : (
        <p className="text-xs text-text-subtle">{t("skills.history.noTextChange")}</p>
      )}
    </div>
  );
}
