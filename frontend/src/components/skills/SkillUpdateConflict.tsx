// src/components/skills/SkillUpdateConflict.tsx
// An update that meets local edits: what was edited here, and the choice — keep the edits, take the update, or compare first.
//
// Spec skill-manager "Update a Git-imported skill from its source": a conflict
// offers Keep mine, Take theirs and Compare instead of a plain preview.
import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { OpChip } from "@/components/change-preview/OpChip";
import { Button } from "@/components/ui/button";
import type { SkillUpdatePreview } from "@/lib/api/skills";
import { CHANGE_OP, shortCommit } from "./skillSourceHelpers";

interface Props {
  name: string;
  preview: SkillUpdatePreview;
  keeping: boolean;
  onKeep: () => void;
  onTake: () => void;
}

function Choice({ title, help, action }: { title: string; help: string; action: ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-raised px-3 py-2.5">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{title}</span>
        <span className="text-xs text-text-muted">{help}</span>
      </div>
      <span className="ml-auto shrink-0">{action}</span>
    </div>
  );
}

export function SkillUpdateConflict({ name, preview, keeping, onKeep, onTake }: Props) {
  const { t } = useTranslation();
  const pinned = shortCommit(preview.from_commit);
  const to = shortCommit(preview.to_commit);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div
        role="status"
        className="flex items-start gap-2.5 rounded-lg bg-warning-soft px-3 py-2.5"
      >
        <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 text-warning" />
        <div className="flex min-w-0 flex-col gap-[3px]">
          <span className="text-sm font-label text-text">
            {t("skillSources.conflict.title", { name })}
          </span>
          <span className="text-xs leading-[1.45] text-text-muted">
            {t("skillSources.conflict.body", { pinned, to })}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-2xs font-semibold text-text-muted">
          {t("skillSources.conflict.localEdits", { count: preview.local_changes.length })}
        </span>
        <ul
          aria-label={t("skillSources.conflict.localEditsLabel")}
          className="flex flex-col rounded-lg border border-border bg-surface-raised"
        >
          {preview.local_changes.map((change) => (
            <li
              key={change.path}
              className="flex min-w-0 items-center gap-2 border-t border-border-subtle px-3 py-1.5 first:border-t-0"
            >
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">
                {change.path}
              </span>
              <LineCounts added={change.additions} removed={change.deletions} />
              <OpChip op={CHANGE_OP[change.status]} size="sm" />
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-2">
        <Choice
          title={t("skillSources.conflict.keep")}
          help={t("skillSources.conflict.keepHelp", { pinned })}
          action={
            <Button type="button" variant="outline" size="sm" disabled={keeping} onClick={onKeep}>
              {keeping ? t("skillSources.conflict.keeping") : t("skillSources.conflict.keep")}
            </Button>
          }
        />
        <Choice
          title={t("skillSources.conflict.take")}
          help={t("skillSources.conflict.takeHelp", { to })}
          action={
            <Button type="button" variant="outline" size="sm" onClick={onTake}>
              {t("skillSources.conflict.take")}
            </Button>
          }
        />
      </div>
    </div>
  );
}
