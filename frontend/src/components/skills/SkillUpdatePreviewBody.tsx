// src/components/skills/SkillUpdatePreviewBody.tsx
// The plain update preview: the commits in the range, then the changed files beside the selected file's diff.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { SkillUpdatePreview } from "@/lib/api/skills";
import { SkillUpdateChanges } from "./SkillUpdateChanges";
import { shortCommit } from "./skillSourceHelpers";

interface Props {
  preview: SkillUpdatePreview;
}

export function SkillUpdatePreviewBody({ preview }: Props) {
  const { t } = useTranslation();
  const [file, setFile] = useState<string | null>(null);
  return (
    <div className="flex min-h-0 flex-col gap-4">
      {preview.commits.length > 0 ? (
        <div className="flex flex-col gap-1">
          <span className="text-2xs font-semibold text-text-muted">
            {t("skillSources.update.commits", { count: preview.commits.length })}
          </span>
          <ul className="flex flex-col gap-0.5" aria-label={t("skillSources.update.commitsLabel")}>
            {preview.commits.map((commit) => (
              <li key={commit.id} className="flex min-w-0 gap-2 text-xs">
                <span className="shrink-0 font-mono text-text-muted">{shortCommit(commit.id)}</span>
                <span className="min-w-0 truncate text-text">{commit.subject}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <SkillUpdateChanges
        changes={preview.changes}
        selected={file}
        onSelect={setFile}
        label={t("skillSources.update.changes", { count: preview.changes.length })}
      />
    </div>
  );
}
