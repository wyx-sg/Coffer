// frontend/src/components/workflow/TemplateRenameDialog.tsx
// What a workflow is CALLED and what it is FOR — the two fields that are not
// part of its shape (spec resource-framework FR-010, spec workflow FR-054).
//
// They used to live in a Settings tab beside two run-wide numbers that have
// since moved onto the tasks they bound. With those gone the tab held one
// editable field and a heading, which is a worse place to look for a name than
// the header the name is printed in — so Edit on the header opens this.
//
// The name goes through the kind-agnostic PATCH, which renames a kind that
// declares it may be renamed and refuses one that does not. A workflow may:
// the only thing that records a template's name is a run's `template_ref`,
// which is provenance and already dangles when the template is deleted.
//
// The description is written in BOTH places on purpose. A workflow carries one
// as a resource and one inside its config, and the config's is what the page
// reads — writing only the resource's would leave the header showing the old
// words with no way to tell why.
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
import { useRenameWorkflowTemplate, type WorkflowTemplate } from "@/lib/hooks/useWorkflowTemplates";

interface Props {
  template: WorkflowTemplate;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where to go when the name changed — the URL carries it. */
  onRenamed: (name: string) => void;
}

export function TemplateRenameDialog({ template, open, onOpenChange, onRenamed }: Props) {
  const { t } = useTranslation();
  const rename = useRenameWorkflowTemplate();
  const [name, setName] = useState(template.name);
  const [description, setDescription] = useState(
    template.config.description ?? template.description ?? "",
  );

  // Reopening after a cancel must not show what was abandoned.
  useEffect(() => {
    if (!open) return;
    setName(template.name);
    setDescription(template.config.description ?? template.description ?? "");
    rename.reset();
    // `rename` is a stable mutation object; re-running on its identity would
    // reset the fields under the developer's cursor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, template]);

  const trimmed = name.trim();
  const unchanged =
    trimmed === template.name &&
    description === (template.config.description ?? template.description ?? "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.templates.editTitle")}</DialogTitle>
          <DialogDescription>{t("workflow.templates.editDescription")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="template-name">{t("workflow.templates.nameField")}</Label>
            <Input
              id="template-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="template-description">{t("workflow.templates.descriptionField")}</Label>
            <Textarea
              id="template-description"
              rows={3}
              value={description}
              placeholder={t("workflow.templates.descriptionPlaceholder")}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {rename.error ? (
            <p className="text-sm text-destructive" role="alert">
              {translateApiError(t, rename.error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={trimmed.length === 0 || unchanged || rename.isPending}
            onClick={async () => {
              // Closes only on success: a refused name stays on screen with the
              // reason, rather than vanishing and leaving the old one.
              await rename.mutateAsync({
                name: template.name,
                newName: trimmed,
                description,
                config: template.config,
              });
              onOpenChange(false);
              if (trimmed !== template.name) onRenamed(trimmed);
            }}
          >
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
