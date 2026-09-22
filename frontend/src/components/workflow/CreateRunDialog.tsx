// frontend/src/components/workflow/CreateRunDialog.tsx
// Create a run: a template and a title. Nothing else (FR-011).
//
// It asked for a working directory once, and for the inputs the run opens
// with. Both are gone. Coffer makes the run its own working directory, so
// there is nothing to pick and nothing to get wrong — the run's page SHOWS
// where the agent is working, but nothing sets it. Inputs are mounted on the
// run's own page, where they can be added and removed for the whole of its
// life (FR-050) rather than only in the five seconds before it exists.
//
// The run lands in `draft`, not `running` — creating and starting are two
// decisions, and mounting the PRD before the first task opens is the reason.
//
// The template list is the generic resource list for kind `workflow`
// (FR-001), so a template registered from the CLI or arriving over sync shows
// up here without this dialog knowing anything about it.
//
// The picker's VALUE is the workflow's uid and its label is the name. The run
// is created from the uid because a run created from a label would be created
// from whatever that label pointed at when the request landed — and the list
// this picker was filled from is a snapshot that a rename elsewhere can age.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useCreateRun } from "@/lib/hooks/useWorkflowRuns";
import { useWorkflowTemplates } from "@/lib/hooks/useWorkflowTemplates";

export function CreateRunDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Only the enabled ones: a disabled workflow starts no new runs (FR-066),
  // and the daemon refuses one, so offering it here would be offering a
  // refusal. The rule is the daemon's; this is the courtesy of not asking.
  const { templates } = useWorkflowTemplates();
  const available = templates.filter((resource) => resource.enabled);
  const create = useCreateRun();
  const [templateUid, setTemplateUid] = useState("");
  const [title, setTitle] = useState("");

  const incomplete = templateUid.length === 0 || title.trim().length === 0;

  const submit = () => {
    create.mutate(
      { template_uid: templateUid, title: title.trim() },
      {
        onSuccess: (run) => {
          onOpenChange(false);
          navigate(`/runs/${run.id}`);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.create.title")}</DialogTitle>
          <DialogDescription>{t("workflow.create.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="run-template">{t("workflow.create.templateLabel")}</Label>
            <Select value={templateUid} onValueChange={setTemplateUid}>
              <SelectTrigger id="run-template">
                <SelectValue placeholder={t("workflow.create.templatePlaceholder")} />
              </SelectTrigger>
              <SelectContent>
                {available.map((resource) => (
                  <SelectItem key={resource.uid} value={resource.uid}>
                    {resource.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {available.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("workflow.create.noneEnabled")}</p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="run-title">{t("workflow.create.titleLabel")}</Label>
            <Input id="run-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          {create.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, create.error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={incomplete || create.isPending} onClick={submit}>
            {t("workflow.create.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
