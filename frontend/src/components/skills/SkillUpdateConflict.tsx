// src/components/skills/SkillUpdateConflict.tsx
// An update that meets local edits (canvas 4.3.22): "terraform-plan changed on
// both sides", the 1060 two-way choice — Keep my edits (the skill stays pinned,
// Coffer says so again at a newer update) or Take the update (the edits are
// replaced and kept in History) — with the diff of the side you are not keeping:
// for each file you edited, your version → the update, or back. Nothing is
// written until the primary is pressed; it names the chosen write.
//
// Spec skill-manager "Update a Git-imported skill from its source".
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { Skeleton } from "@/components/ui/skeleton";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import type { SkillOut, SkillUpdatePreview } from "@/lib/api/skills";
import { useSkillUpdateCompare } from "@/lib/hooks/useSkills";
import { SkillChoiceDialog } from "./SkillChoiceDialog";
import { useHolderSummaries } from "./skillSummaries";
import { shortCommit } from "./skillSourceHelpers";
import { textChangeItem } from "./textDiff";

type Keep = "keep" | "take";

interface Props {
  skill: SkillOut;
  preview: SkillUpdatePreview;
  open: boolean;
  onClose: () => void;
  onKeep: () => void;
  onTake: () => void;
  pending: boolean;
  error: unknown;
}

/** One edited file: your version against the update's, in the direction the choice makes. */
function ConflictFile({
  uid,
  stagingId,
  path,
  keep,
}: {
  uid: string;
  stagingId: string;
  path: string;
  keep: Keep;
}) {
  const { t } = useTranslation();
  const compare = useSkillUpdateCompare(uid, stagingId, path);
  if (compare.error) {
    return (
      <p role="alert" className="text-xs text-danger">
        {translateApiError(t, compare.error)}
      </p>
    );
  }
  if (!compare.data) return <Skeleton className="h-24 w-full" />;
  const { local, incoming } = compare.data;
  if (local.text === null || incoming.text === null || local.binary || incoming.binary) {
    return (
      <p className="text-xs text-text-muted">
        <span className="font-mono">{path}</span> · {t("skillSources.compare.binary")}
      </p>
    );
  }
  // Taking the update changes your version into the update's; keeping yours
  // changes the update's into yours — the diff is the change to the side
  // that is not kept.
  const item =
    keep === "take"
      ? textChangeItem(path, path, local.text, incoming.text)
      : textChangeItem(path, path, incoming.text, local.text);
  return <FileDiff item={item} />;
}

export function SkillUpdateConflict({
  skill,
  preview,
  open,
  onClose,
  onKeep,
  onTake,
  pending,
  error,
}: Props) {
  const { t } = useTranslation();
  const [keep, setKeep] = useState<Keep>("take");
  const pinned = shortCommit(preview.from_commit);
  const to = shortCommit(preview.to_commit);
  const summaries = useHolderSummaries(
    skill,
    keep === "take"
      ? t("skills.conflict.cofferTake", { name: skill.name, to })
      : t("skills.conflict.cofferKeep", { name: skill.name, pinned }),
    keep === "take" ? t("skills.conflict.agentTake") : t("skills.conflict.agentKeep"),
  );
  const paths = preview.local_changes.map((c) => c.path);

  return (
    <SkillChoiceDialog<Keep>
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={
        <>
          <span className="font-mono text-md">{skill.name}</span>
          {t("skills.update.bothSides")}
        </>
      }
      subtitle={t("skillSources.conflict.body", { pinned, to })}
      groupLabel={t("skillSources.conflict.title", { name: skill.name })}
      choices={[
        {
          value: "keep",
          title: t("skillSources.conflict.keep"),
          help: t("skillSources.conflict.keepHelp", { pinned }),
        },
        {
          value: "take",
          title: t("skillSources.conflict.take"),
          help: t("skillSources.conflict.takeHelp", { to }),
        },
      ]}
      value={keep}
      onChange={setKeep}
      happen={summaries}
      confirmLabel={
        keep === "keep" ? t("skillSources.conflict.keep") : t("skillSources.conflict.take")
      }
      onConfirm={keep === "keep" ? onKeep : onTake}
      pending={pending}
      error={
        error ? (
          <DialogErrorBanner
            title={t("skills.update.failed")}
            message={translateApiError(t, error)}
          />
        ) : null
      }
    >
      {paths.map((path) => (
        <ConflictFile
          key={`${keep}:${path}`}
          uid={skill.uid}
          stagingId={preview.staging_id}
          path={path}
          keep={keep}
        />
      ))}
      <p className="text-xs text-text-muted">
        {keep === "take"
          ? t("skills.conflict.captionTake", { to })
          : t("skills.conflict.captionKeep", { to })}
      </p>
    </SkillChoiceDialog>
  );
}
