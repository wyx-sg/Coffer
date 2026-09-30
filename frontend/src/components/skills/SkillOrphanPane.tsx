// frontend/src/components/skills/SkillOrphanPane.tsx
// One folder in the skills store that is not in the library (canvas 4.3.28):
// where it is, whether its SKILL.md is valid and how many files it holds, why
// no agent gets it, and the three things to do — Add to library… (registers
// the folder in place, reach as for a fresh import), Reveal in Finder, and
// Delete folder… (moved to ~/.coffer/content/backup/, confirmed first).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Folder, FolderOpen, Plus, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useFsActions } from "@/lib/fsActions";
import {
  useAdoptSkillOrphan,
  useRemoveSkillOrphan,
  useSkillOrphans,
} from "@/lib/hooks/useSkillCopies";

export function SkillOrphanPane({ name }: { name: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const fs = useFsActions();
  const orphans = useSkillOrphans();
  const adopt = useAdoptSkillOrphan();
  const remove = useRemoveSkillOrphan();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const orphan = orphans.data?.find((o) => o.name === name);

  if (!orphan) {
    return orphans.isPending ? null : (
      <EmptyState icon={Folder} title={t("skills.orphan.gone", { name })} />
    );
  }
  const facts = [
    orphan.valid ? t("skills.orphan.valid") : t("skills.orphan.invalid"),
    t("skills.orphan.files", { count: orphan.file_count }),
  ].join(" · ");

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-border-subtle p-4">
      <div className="flex items-start gap-3">
        <span className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-lg bg-warning-soft text-warning">
          <Folder className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="font-mono text-lg font-bold">{orphan.name}</h2>
          <p className="text-xs text-text-muted">
            <span className="font-mono">{abbreviateHomePath(orphan.path)}</span> · {facts}
          </p>
        </div>
      </div>
      <p className="text-sm text-text-muted">{t("skills.orphan.body")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          disabled={!orphan.valid || adopt.isPending}
          onClick={() =>
            adopt.mutate(orphan.name, {
              onSuccess: (skill) => navigate(`/skills/${encodeURIComponent(skill.name)}`),
            })
          }
        >
          <Plus aria-hidden /> {t("skills.orphan.add")}
        </Button>
        <Button
          variant="outline"
          onClick={() =>
            void fs.reveal(orphan.path).catch(() => toast.error(t("fileActions.revealFailed")))
          }
        >
          <FolderOpen aria-hidden /> {t("fileActions.reveal")}
        </Button>
        <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
          <Trash2 aria-hidden /> {t("skills.orphan.delete")}
        </Button>
      </div>
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
    </section>
  );
}
