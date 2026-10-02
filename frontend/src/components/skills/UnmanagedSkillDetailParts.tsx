// frontend/src/components/skills/UnmanagedSkillDetailParts.tsx — spec
// skill-manager "Preview an unmanaged skill read-only".
// The pieces of UnmanagedSkillDetailPage kept out of the page file for its size
// budget: the header badges, the header actions (open folder / adopt / delete)
// and the Overview card.
//
// The actions are the ones the agent's Skills table used to carry per row, and
// they behave the same way here: open folder goes through the loopback daemon to
// the OS file manager; adopt is refused up front for a folder that cannot be
// adopted (invalid, or a foreign link) and on success moves to the new managed
// skill's own page, since this folder no longer exists as an unmanaged entry;
// delete asks first and on success returns to where the reader came from.
// Adopt/delete failures toast from the hooks.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, FolderOpen, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { UnmanagedSkillDetailOut } from "@/lib/api/agents-workspace";
import { useFsActions } from "@/lib/fsActions";
import { useAdoptUnmanagedSkill, useDeleteUnmanagedSkill } from "@/lib/hooks/useAgents";

type Skill = UnmanagedSkillDetailOut;

export function UnmanagedSkillBadges({ skill }: { skill: Skill }) {
  const { t } = useTranslation();
  return (
    <>
      <Badge variant="outline" data-testid="unmanaged-badge">
        {t("agents.skillsTab.unmanagedBadge")}
      </Badge>
      <Badge variant="outline">
        {skill.location === "agents_dir"
          ? t("agents.skillsTab.locationAgentsDir")
          : t("agents.skillsTab.locationSkills")}
      </Badge>
      {skill.foreign_link ? (
        <Badge variant="outline" className="border-status-warn/50 text-status-warn">
          {t("agents.skillsTab.foreignLink")}
        </Badge>
      ) : null}
    </>
  );
}

export function UnmanagedSkillActions({
  agentUid,
  skill,
  backTo,
}: {
  agentUid: string;
  skill: Skill;
  /** Where a successful delete returns to: the agent's Skills tab. */
  backTo: string;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const { open } = useFsActions();
  const adopt = useAdoptUnmanagedSkill(agentUid);
  const remove = useDeleteUnmanagedSkill(agentUid);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const adoptHint = !skill.valid
    ? t("agents.skillsTab.adoptDisabledInvalid")
    : skill.foreign_link
      ? t("agents.skillsTab.adoptDisabledForeign")
      : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          void open(skill.path, "").catch(() => toast.error(t("agents.skillsTab.openFolderFailed")))
        }
      >
        <FolderOpen className="mr-1.5 size-3.5" /> {t("agents.skillsTab.openFolder")}
      </Button>
      {/* The wrapper carries the disabled reason — a disabled button fires no
          pointer events, so it cannot show a title of its own. */}
      <span title={adoptHint}>
        <Button
          variant="outline"
          size="sm"
          disabled={!skill.valid || skill.foreign_link || adopt.isPending}
          onClick={() =>
            adopt.mutate(
              { skill: skill.name, location: skill.location },
              {
                onSuccess: (ref) => {
                  toast.success(t("agents.skillsTab.adoptSuccess", { name: ref.name }));
                  navigate(`/skills/${encodeURIComponent(ref.name)}`);
                },
              },
            )
          }
        >
          {t("agents.skillsTab.adopt")}
        </Button>
      </span>
      <Button
        variant="outline"
        size="sm"
        className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
        onClick={() => setDeleteOpen(true)}
      >
        <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
      </Button>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("agents.removeConfirmTitle", { name: skill.name })}
        description={t("agents.skillsTab.deleteConfirm")}
        confirmLabel={t("common.delete")}
        pending={remove.isPending}
        onConfirm={() =>
          // Close only on success; the hook toasts a failure.
          remove.mutate(
            { skill: skill.name, location: skill.location },
            {
              onSuccess: () => {
                setDeleteOpen(false);
                navigate(backTo);
              },
            },
          )
        }
      />
    </div>
  );
}

/** Why the folder is not a skill Coffer can adopt, shown before anything else. */
export function UnmanagedSkillInvalidNotice({ reason }: { reason: string | null }) {
  const { t } = useTranslation();
  return (
    <Card className="border-status-warn/50" role="alert" data-testid="unmanaged-invalid">
      <CardContent className="flex items-start gap-3 py-4">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-status-warn" aria-hidden />
        <div className="space-y-1 text-sm">
          <p className="font-medium">{t("agents.skillsTab.unmanagedDetail.invalidTitle")}</p>
          {reason ? <p className="text-muted-foreground">{reason}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function UnmanagedSkillOverview({ skill }: { skill: Skill }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardContent className="space-y-4 py-6">
        {skill.description ? (
          <p className="max-w-prose text-sm text-muted-foreground">{skill.description}</p>
        ) : null}
        <dl className="grid gap-y-3 text-sm sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted-foreground">{t("agents.skillsTab.unmanagedDetail.path")}</dt>
          <dd className="break-all font-mono text-xs">{skill.path}</dd>

          <dt className="text-muted-foreground">
            {t("agents.skillsTab.unmanagedDetail.location")}
          </dt>
          <dd>
            {skill.location === "agents_dir"
              ? t("agents.skillsTab.locationAgentsDir")
              : t("agents.skillsTab.locationSkills")}
          </dd>
        </dl>
        <p className="text-xs text-muted-foreground">
          {t("agents.skillsTab.unmanagedDetail.readOnlyHint")}
        </p>
      </CardContent>
    </Card>
  );
}
