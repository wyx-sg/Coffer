// frontend/src/components/workflow/TemplateCreateDialog.tsx
// Creating a template asks the two things a form cannot infer — its name and
// what it is for — and then opens the editor on it.
//
// It is registered with a real, runnable shell (one stage, one task), not an
// empty one: the contract's minima are one stage and one node per stage, so an
// empty template is a template that cannot be stored. The developer lands in
// the editor with something to rename rather than a refusal to decode.
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
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import { useCreateWorkflowTemplate } from "@/lib/hooks/useWorkflowTemplates";
import { emptyTemplate } from "@/lib/workflow/templateDraft";

export function TemplateCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateWorkflowTemplate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const submit = () => {
    const trimmed = name.trim();
    const about = description.trim();
    create.mutate(
      {
        name: trimmed,
        description: about.length > 0 ? about : null,
        config: { ...emptyTemplate(), description: about.length > 0 ? about : null },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setName("");
          setDescription("");
          navigate(`/workflows/${encodeURIComponent(trimmed)}`);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.templates.createTitle")}</DialogTitle>
          <DialogDescription>{t("workflow.templates.createDescription")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="template-name">{t("workflow.templates.nameLabel")}</Label>
            <Input
              id="template-name"
              value={name}
              placeholder={t("workflow.templates.namePlaceholder")}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="template-about">{t("workflow.templates.description")}</Label>
            <Textarea
              id="template-about"
              rows={2}
              value={description}
              placeholder={t("workflow.templates.descriptionPlaceholder")}
              onChange={(e) => setDescription(e.target.value)}
            />
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
          <Button disabled={name.trim().length === 0 || create.isPending} onClick={submit}>
            {t("workflow.templates.createSubmit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
