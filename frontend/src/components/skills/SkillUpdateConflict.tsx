// src/components/skills/SkillUpdateConflict.tsx
// An update that meets local edits (canvas 4.3.19): "changed on both sides",
// then the confirmed choices — Keep my edits (stays pinned; Coffer says so
// again at a newer update), Take the update (your edits are replaced), or
// Merge with an agent (the backend's hand-off asks your agent to merge the
// update into your edits in the master folder; I merged it then records it) —
// over the files you edited here. The dialog's footer carries the confirm
// button for the chosen card; Compare opens the three versions of a file.
//
// Spec skill-manager "Update a Git-imported skill from its source" and
// "Record an update merged into local edits".
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { SkillChoiceCards } from "@/components/skills/SkillChoiceCards";
import type { SkillUpdatePreview } from "@/lib/api/skills";
import { shortCommit } from "./skillSourceHelpers";
import { SkillUpdateDiff } from "./SkillUpdateDiff";

export type ConflictChoice = "keep" | "take" | "merge";

interface Props {
  name: string;
  preview: SkillUpdatePreview;
  choice: ConflictChoice | null;
  onChoose: (choice: ConflictChoice) => void;
}

export function SkillUpdateConflict({ name, preview, choice, onChoose }: Props) {
  const { t } = useTranslation();
  const pinned = shortCommit(preview.from_commit);
  const to = shortCommit(preview.to_commit);
  const handoff = preview.handoff;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="text-xs text-text-muted">{t("skillSources.conflict.body", { pinned, to })}</p>
      <SkillChoiceCards<ConflictChoice>
        label={t("skillSources.conflict.title", { name })}
        value={choice}
        onChange={onChoose}
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
          ...(handoff
            ? [
                {
                  value: "merge" as const,
                  title: t("skillSources.conflict.merge"),
                  help: t("skillSources.conflict.mergeHelp"),
                },
              ]
            : []),
        ]}
      />
      {choice === "merge" && handoff ? (
        <div
          data-testid="skill-update-merge-handoff"
          className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface-sunken px-3.5 py-3"
        >
          <p className="text-xs text-text-muted">
            {t("skillSources.conflict.mergeBody", { to, name })}
          </p>
          <AgentHandoff prompt={handoff.prompt} size="sm" />
        </div>
      ) : null}
      <div className="flex flex-col gap-3" aria-label={t("skillSources.conflict.localEditsLabel")}>
        {preview.local_changes.map((change) => (
          <SkillUpdateDiff key={change.path} change={change} />
        ))}
      </div>
    </div>
  );
}
