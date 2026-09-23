// frontend/src/components/workflow/RunRelabelDialog.tsx
// What a run is CALLED and what it is for (spec workflow "Edit a run's title and description
// as labels").
//
// The title is typed at the moment the developer knows least about the work —
// before the first task has opened — and until this dialog existed it could
// never be corrected. In a list of forty deliveries the title is the only
// thing that tells one from another, so a label you cannot fix is a list you
// stop reading.
//
// It is the ONE in-place edit of a run, and it carries no version. A run's
// status, its stage and its position are folded from its event log and only
// the engine writes them; this touches none of them and appends no
// event. A run another machine advances refuses it like every other change,
// which is why the caller hides it there rather than letting the
// daemon be the only one to say no.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import { useRelabelRun } from "@/lib/hooks/useWorkflowRun";

interface Props {
  runId: string;
  title: string;
  description: string | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RunRelabelDialog({ runId, title, description, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const relabel = useRelabelRun(runId);
  const [name, setName] = useState(title);
  const [about, setAbout] = useState(description ?? "");

  // Reopening after a cancel must not show what was abandoned.
  useEffect(() => {
    if (!open) return;
    setName(title);
    setAbout(description ?? "");
    relabel.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, title, description]);

  const trimmed = name.trim();
  const unchanged = trimmed === title && about === (description ?? "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.run.editTitle")}</DialogTitle>
          <DialogDescription>{t("workflow.run.editDescription")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="run-title">{t("workflow.run.titleField")}</Label>
            <Input
              id="run-title"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="run-description">{t("workflow.run.descriptionField")}</Label>
            <Textarea
              id="run-description"
              rows={3}
              value={about}
              placeholder={t("workflow.run.descriptionPlaceholder")}
              onChange={(e) => setAbout(e.target.value)}
            />
          </div>
          {relabel.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, relabel.error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={trimmed.length === 0 || unchanged || relabel.isPending}
            onClick={async () => {
              // Closes only on success: a refused edit stays on screen with the
              // reason rather than vanishing and leaving the old words.
              await relabel.mutateAsync({ title: trimmed, description: about || null });
              onOpenChange(false);
            }}
          >
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
