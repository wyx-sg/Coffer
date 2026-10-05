// frontend/src/components/skills/SkillUpdateBanner.tsx
// "An update is available from <repo>" on a Git-imported skill (spec
// skill-manager "Hand a Git-imported skill's update to an agent"). Coffer does
// not apply the update and draws no diff: the one primary action is the
// hand-off split button — Hand off to <Agent> to update, the prompt fetched
// from the daemon when a verb is picked — with I merged it beside it (confirmed
// first; it pins the skill to the commit the agent merged). The change itself
// is looked at outside Coffer: Open in editor opens the master folder, and View
// upstream changes the compare page of GitHub or GitLab; any other host gets
// the commit range, which can be copied, and the commits' subjects.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Info } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { GitImportSource, SkillOut } from "@/lib/api/skills";
import { useFsActions } from "@/lib/fsActions";
import { useRecordSkillMerged, useSkillUpdateHandoff } from "@/lib/hooks/useSkills";
import { usePreferredEditor } from "@/lib/preferences";
import { folderLabel } from "@/lib/skills/format";
import { repoLabel, shortCommit } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
  source: GitImportSource;
}

export function SkillUpdateBanner({ skill, source }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const editor = usePreferredEditor();
  const requestPrompt = useSkillUpdateHandoff(skill.uid);
  const merged = useRecordSkillMerged();
  const [confirming, setConfirming] = useState(false);
  const status = skill.source_status;
  const latest = status?.latest_commit ?? "";
  const range = `${shortCommit(source.commit)}..${shortCommit(latest)}`;
  const compareUrl = status?.compare_url ?? null;
  const commits = status?.commits ?? [];

  const copyRange = () =>
    void navigator.clipboard.writeText(range).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("skills.menu.copyFailed")),
    );

  return (
    <Alert variant="info" data-testid="skill-banner-update">
      <Info aria-hidden />
      <div className="flex flex-col gap-2.5">
        <div className="min-w-0">
          <AlertTitle>{t("skills.banner.updateTitle", { repo: repoLabel(source.url) })}</AlertTitle>
          <AlertDescription>
            {t("skills.banner.updateBody", {
              ref: source.ref ?? t("skills.banner.defaultBranch"),
              count: status?.commits_ahead ?? 0,
              commit: shortCommit(source.commit),
              files: status?.files_changed ?? 0,
              folder: folderLabel(source.subpath) ?? t("skills.banner.repoTop"),
            })}
          </AlertDescription>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <AgentHandoff
            size="sm"
            prompt={requestPrompt}
            label={(agent) => t("skills.update.handoff", { agent })}
          />
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            {t("skills.update.merged")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              void fs
                .open(skill.master_path, editor)
                .catch(() => toast.error(t("fileActions.openFailed")))
            }
          >
            {t("fileActions.openInEditor")}
          </Button>
          {compareUrl ? (
            <Button variant="ghost" size="sm" asChild>
              <a href={compareUrl} target="_blank" rel="noreferrer">
                {t("skills.update.viewUpstream")}
              </a>
            </Button>
          ) : null}
        </div>

        {compareUrl ? null : (
          <div className="flex flex-col gap-1.5" data-testid="skill-update-range">
            <span className="flex items-center gap-1.5 text-xs text-text-muted">
              {t("skills.update.range")}
              <span className="font-mono">{range}</span>
              <Button
                variant="ghost"
                size="sm"
                aria-label={t("skills.update.copyRange")}
                onClick={copyRange}
              >
                <Copy aria-hidden />
              </Button>
            </span>
            {commits.length > 0 ? (
              <ul className="flex flex-col gap-0.5 text-xs text-text-muted">
                {commits.map((c) => (
                  <li key={c.id} className="truncate">
                    <span className="font-mono">{shortCommit(c.id)}</span> {c.subject}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        variant="default"
        title={t("skills.update.mergedTitle", { name: skill.name })}
        description={t("skills.update.mergedBody", { commit: shortCommit(latest) })}
        confirmLabel={t("skills.update.merged")}
        errorTitle={t("skills.update.mergedFailed")}
        pending={merged.isPending}
        error={merged.error}
        onConfirm={() =>
          merged.mutate(
            { uid: skill.uid, commit: latest },
            {
              onSuccess: () => {
                setConfirming(false);
                toast.success(
                  t("skills.update.mergedDone", {
                    name: skill.name,
                    commit: shortCommit(latest),
                  }),
                );
              },
            },
          )
        }
      />
    </Alert>
  );
}
