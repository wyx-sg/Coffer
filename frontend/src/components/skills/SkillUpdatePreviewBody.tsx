// src/components/skills/SkillUpdatePreviewBody.tsx
// The plain update preview (canvas 4.3.18): what will happen — Coffer moves
// the skill to the new commit, and every agent with a link sees the new files
// at once — then the changed files beside the selected file's diff, and the
// commits in the range on one line under it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkle } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import type { SkillOut, SkillUpdatePreview } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { SkillUpdateChanges } from "./SkillUpdateChanges";
import { shortCommit } from "./skillSourceHelpers";

interface Props {
  preview: SkillUpdatePreview;
  /** The skill being updated, for "What will happen". */
  skill?: SkillOut;
}

function WhatWillHappen({ skill, preview }: { skill: SkillOut; preview: SkillUpdatePreview }) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const holders = skill.bindings.map((b) => ({
    uid: b.agent_uid,
    agent: agents.find((a) => a.uid === b.agent_uid),
    name: b.agent_name,
  }));
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-surface-sunken p-3">
      <span className="text-2xs font-semibold uppercase tracking-[.04em] text-text-subtle">
        {t("skills.update.whatWillHappen")}
      </span>
      <p className="flex gap-2 text-xs leading-[1.45] text-text-muted">
        <Sparkle className="mt-0.5 size-3.5 shrink-0 text-text-subtle" aria-hidden />
        <span>
          <span className="font-label text-text">{t("skills.update.coffer")}</span>{" "}
          {t("skills.update.cofferMoves", {
            name: skill.name,
            from: shortCommit(preview.from_commit),
            to: shortCommit(preview.to_commit),
          })}
        </span>
      </p>
      {holders.map((h) => (
        <p key={h.uid} className="flex gap-2 text-xs leading-[1.45] text-text-muted">
          <AgentBadge type={h.agent?.type ?? ""} name={h.agent?.display_name ?? h.name} size="sm" />
          <span>
            <span className="font-label text-text">{h.agent?.display_name ?? h.name}.</span>{" "}
            {t("skills.update.agentSees")}
          </span>
        </p>
      ))}
    </div>
  );
}

export function SkillUpdatePreviewBody({ preview, skill }: Props) {
  const { t } = useTranslation();
  const [file, setFile] = useState<string | null>(null);
  return (
    <div className="flex min-h-0 flex-col gap-4">
      {skill ? <WhatWillHappen skill={skill} preview={preview} /> : null}
      <SkillUpdateChanges
        changes={preview.changes}
        selected={file}
        onSelect={setFile}
        label={t("skillSources.update.changes", { count: preview.changes.length })}
      />
      {preview.commits.length > 0 ? (
        <p className="text-xs text-text-muted" aria-label={t("skillSources.update.commitsLabel")}>
          {t("skills.update.commitsLine", {
            count: preview.commits.length,
            subjects: preview.commits.map((c) => `“${c.subject}”`).join(", "),
          })}
        </p>
      ) : null}
    </div>
  );
}
