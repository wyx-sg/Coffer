// frontend/src/components/skills/SkillOrphanPane.tsx
// One folder in the skills store that is not in the library (canvas 4.3.03),
// laid out like a skill: a header (folder tile, name, the "Not in your library"
// pill, a meta line with where it is, whether its SKILL.md is valid and how
// many files it holds, and Reveal in Finder on the right), then a banner that
// says why no agent gets it and carries the two things to do — Add to library
// (registers the folder in place, reach as for a fresh import) and Delete
// folder… (moved to ~/.coffer/content/backup/, confirmed first). Adding or
// deleting is the person's choice, so there is no hand-off. Below the banner
// sits the folder's own files in the read-only tree + reader a skill outside
// the library gets (SkillReadOnlyFiles), no section title.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Folder, FolderOpen } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { SkillBannerFrame } from "@/components/skills/SkillBannerFrame";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { SkillReadOnlyFiles } from "@/components/skills/SkillReadOnlyFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useFsActions } from "@/lib/fsActions";
import { formatDayShort } from "@/lib/time";
import {
  useAdoptSkillOrphan,
  useRemoveSkillOrphan,
  useSkillOrphanFileContent,
  useSkillOrphanFiles,
  useSkillOrphans,
} from "@/lib/hooks/useSkillCopies";

export function SkillOrphanPane({ name }: { name: string }) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const fs = useFsActions();
  const orphans = useSkillOrphans();
  const adopt = useAdoptSkillOrphan();
  const remove = useRemoveSkillOrphan();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const orphan = orphans.data?.find((o) => o.name === name);
  const tree = useSkillOrphanFiles(name);
  const useContent = (path: string) => useSkillOrphanFileContent(name, path);

  if (!orphan) {
    return orphans.isPending ? null : (
      <EmptyState icon={Folder} title={t("skills.orphan.gone", { name })} />
    );
  }
  const facts = [
    orphan.valid ? t("skills.orphan.valid") : t("skills.orphan.invalid"),
    t("skills.orphan.files", { count: orphan.file_count }),
    t("skills.orphan.found", { day: formatDayShort(new Date(orphan.found_at), i18n.language) }),
  ];

  return (
    <div className="flex min-w-0 flex-col gap-[18px]">
      <header className="flex min-w-0 items-center gap-3">
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-warning-soft text-warning">
          <Folder className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
          <div className="flex min-w-0 items-center gap-2.5">
            <h2 className="min-w-0 truncate font-mono text-lg font-semibold">{orphan.name}</h2>
            <StatusPill tone="warn" className="shrink-0">
              {t("skills.orphan.section")}
            </StatusPill>
          </div>
          <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-text-muted">
            <span className="font-mono">{abbreviateHomePath(orphan.path)}</span>
            {facts.map((fact) => (
              <span key={fact} className="inline-flex items-center gap-1.5">
                <span aria-hidden className="text-text-subtle">
                  ·
                </span>
                {fact}
              </span>
            ))}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() =>
            void fs.reveal(orphan.path).catch(() => toast.error(t("fileActions.revealFailed")))
          }
        >
          <FolderOpen aria-hidden /> {t("fileActions.reveal")}
        </Button>
      </header>
      <SkillBannerFrame
        tone="warning"
        testId="skill-orphan-banner"
        title={t("skills.orphan.bannerTitle")}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={!orphan.valid || adopt.isPending}
              onClick={() =>
                adopt.mutate(orphan.name, {
                  onSuccess: (skill) => navigate(`/skills/${encodeURIComponent(skill.name)}`),
                })
              }
            >
              {t("skills.orphan.add")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>
              {t("skills.orphan.delete")}
            </Button>
          </>
        }
      >
        {t("skills.orphan.body")}
      </SkillBannerFrame>
      <SkillReadOnlyFiles
        name={orphan.name}
        tree={tree}
        useContent={useContent}
        folderPath={orphan.path}
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t("skills.orphan.deleteTitle", { name: orphan.name })}
        description={t("skills.orphan.deleteBody")}
        confirmLabel={t("skills.orphan.deleteConfirm")}
        pending={remove.isPending}
        error={remove.error ?? undefined}
        onConfirm={() =>
          remove.mutate(orphan.name, {
            onSuccess: () => {
              setConfirmDelete(false);
              navigate("/skills", { replace: true });
            },
          })
        }
      />
    </div>
  );
}
