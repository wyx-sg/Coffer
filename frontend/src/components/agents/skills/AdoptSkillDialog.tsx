// src/components/agents/skills/AdoptSkillDialog.tsx — adopt an unmanaged skill folder into Coffer (boards 2.1.21–2.1.23, 480).
//
// Spec skill-manager "Adopt an unmanaged skill into the master store". Three fields: the name it gets
// in Coffer (checked inline against the library — a taken name says so and
// links to Coffer's skill), where it comes from (read-only, with the files that
// move), and its reach (every agent unless narrowed). Errors stay inside the
// dialog and the button reads Retry; it closes only when the adoption worked.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ReadOnlyCopyField } from "@/components/agents/tabs/ReadOnlyCopyField";
import { ReachControl } from "@/components/reach/ReachControl";
import { Button } from "@/components/ui/button";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath } from "@/lib/agents/display";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useAdoptUnmanagedSkill } from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";
import { useUnmanagedSkillFiles } from "@/lib/hooks/useUnmanagedSkill";
import { EVERY_AGENT, toWire, type SkillReachDraft } from "@/lib/skills/reach";
import type { OwnSkillRow } from "./skillRows";

/** The relative path of every file under the folder, in tree order. */
function filePaths(node: SkillFileNode | undefined): string[] {
  if (!node) return [];
  if (node.type === "file") return [node.path || node.name];
  return node.children.flatMap(filePaths);
}

const FILES_SHOWN = 4;

interface Props {
  agentUid: string;
  /** The folder being adopted; null keeps the dialog closed. */
  row: OwnSkillRow | null;
  onOpenChange: (open: boolean) => void;
  /** Called with the Coffer skill the adoption created, after a success. */
  onAdopted?: (ref: { uid: string; name: string }) => void;
}

export function AdoptSkillDialog({ agentUid, row, onOpenChange, onAdopted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const skills = useSkills();
  const adopt = useAdoptUnmanagedSkill(agentUid, { toastErrors: false });
  const files = useUnmanagedSkillFiles(
    row ? agentUid : "",
    row?.item.location ?? "",
    row?.name ?? "",
  );
  const [name, setName] = useState("");
  const [reach, setReach] = useState<SkillReachDraft>(EVERY_AGENT);
  const [failure, setFailure] = useState<unknown>(null);

  // A fresh form for every folder.
  useEffect(() => {
    setName(row?.name ?? "");
    setReach(EVERY_AGENT);
    setFailure(null);
  }, [row]);

  const trimmed = name.trim();
  const taken = (skills.data ?? []).find((s) => s.name === trimmed);
  const serverConflict =
    failure instanceof ApiError && failure.code.endsWith("ALREADY_EXISTS") ? trimmed : null;
  const conflictName = taken?.name ?? serverConflict;
  const otherFailure = failure && serverConflict === null ? failure : null;

  const paths = filePaths(files.data);
  const shown = paths.slice(0, FILES_SHOWN);
  const more = paths.length - shown.length;

  const submit = () => {
    if (!row) return;
    setFailure(null);
    adopt.mutate(
      {
        skill: row.name,
        location: row.item.location,
        name: trimmed === row.name ? undefined : trimmed,
        reach: toWire(reach),
      },
      {
        onSuccess: (ref) => {
          toast.success(t("agents.skillsTab.adoptSuccess", { name: ref.name }));
          onOpenChange(false);
          onAdopted?.(ref);
        },
        onError: setFailure,
      },
    );
  };

  return (
    <Dialog open={row !== null} onOpenChange={(next) => !adopt.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            {t("agents.skillsTab.adoptDialog.title", { name: row?.name ?? "" })}
          </DialogTitle>
          <DialogDescription>{t("agents.skillsTab.adoptDialog.description")}</DialogDescription>
        </DialogHeader>

        {otherFailure ? (
          <DialogErrorBanner
            title={t("agents.skillsTab.adoptDialog.failedTitle", { name: row?.name ?? "" })}
            message={translateApiError(t, otherFailure)}
          />
        ) : null}

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="adopt-skill-name">{t("agents.skillsTab.adoptDialog.name")}</Label>
            <Input
              id="adopt-skill-name"
              value={name}
              className="font-mono"
              aria-invalid={conflictName !== null || undefined}
              onChange={(e) => setName(e.target.value)}
            />
            {conflictName !== null ? (
              <p className="flex flex-col gap-0.5 text-xs text-danger" role="alert">
                <span>{t("agents.skillsTab.adoptDialog.nameTaken", { name: conflictName })}</span>
                <Link
                  to={`/skills/${encodeURIComponent(conflictName)}`}
                  className="text-accent-text hover:underline"
                >
                  {t("agents.skillsTab.adoptDialog.openTaken", { name: conflictName })}
                </Link>
              </p>
            ) : (
              <p className="text-xs text-text-muted">
                {t("agents.skillsTab.adoptDialog.nameHint")}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>{t("agents.skillsTab.adoptDialog.from")}</Label>
            <ReadOnlyCopyField
              value={row ? abbreviateHomePath(row.item.path) : ""}
              copyLabel={t("agents.skillsTab.adoptDialog.copyPath")}
            />
            {paths.length > 0 ? (
              <p className="text-xs text-text-muted">
                {t("agents.skillsTab.adoptDialog.files", {
                  count: paths.length,
                  names: shown.join(", ") + (more > 0 ? `, +${more}` : ""),
                })}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>{t("agents.skillsTab.adoptDialog.reach")}</Label>
            <div>
              <ReachControl
                mode={reach.mode}
                initialScope={reach.scope}
                ariaLabel={t("agents.skillsTab.adoptDialog.reach")}
                testId="adopt-skill-reach"
                onDisabled={() => setReach({ mode: "disabled", scope: reach.scope })}
                onEverywhere={() => setReach(EVERY_AGENT)}
                onRestricted={(scope) => setReach({ mode: "restricted", scope })}
              />
            </div>
            <p className="text-xs text-text-muted">{t("agents.skillsTab.adoptDialog.reachHint")}</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" disabled={adopt.isPending} onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            loading={adopt.isPending}
            disabled={!trimmed || conflictName !== null}
            onClick={submit}
          >
            {otherFailure ? t("common.retry") : t("agents.skillsTab.adopt")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
