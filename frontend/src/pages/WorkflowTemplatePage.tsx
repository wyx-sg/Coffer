// frontend/src/pages/WorkflowTemplatePage.tsx — spec workflow, FR-054..FR-056.
// The workflow editor: the stages, the tasks inside them, and where work is
// sent back to — authored as a map with a dialog per thing, never in raw JSON.
//
// THERE IS NO SETTINGS TAB. It held three fields: a description, which the
// header already shows and the Edit dialog now writes, and two run-wide
// numbers that turned out to belong elsewhere — the attempt ceiling is each
// task's own (FR-026) and the token budget is gone. A tab holding one field
// that lives somewhere better is a second place to look for it.
//
// THERE IS NO SAVE BUTTON (FR-062). Every edit is written as it is made: a
// dialog's own Save writes the task or the stage it holds, and adding,
// reordering and deleting on the map write themselves. A page-level Save over
// a form with forty inputs in it is a thing to forget to press, and the
// Discard beside it was the only way to undo a typo three tabs away.
//
// It writes through `PATCH /resources/workflow/{name}` like every other client
// of every other kind (FR-056), and it reads a refusal back as the FIELD it
// names (FR-055): `templateRefusal` turns the daemon's answer into a path, and
// the dialog holding that path puts the message on the control.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle, Pencil, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { TemplateFlow } from "@/components/workflow/TemplateFlow";
import { TemplateRenameDialog } from "@/components/workflow/TemplateRenameDialog";
import { WORKFLOW_TEMPLATE_KIND } from "@/lib/api/workflow";
import { translateApiError } from "@/lib/api/errors";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useTemplateEditor } from "@/lib/hooks/useTemplateEditor";
import { useWorkflowTemplate } from "@/lib/hooks/useWorkflowTemplates";
import { templateRefusal } from "@/lib/workflow/templateErrors";

export function WorkflowTemplatePage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: template, isPending, error } = useWorkflowTemplate(name);
  const editor = useTemplateEditor(name);
  const del = useDeleteResource();
  const [deleting, setDeleting] = useState(false);
  const [renaming, setRenaming] = useState(false);

  const refusal = templateRefusal(editor.error);

  const back = { to: "/workflows", label: t("workflow.templates.backToList") };

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-48" />} />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (error || !template) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={name} />
        <EmptyState
          title={t("workflow.templates.notFound")}
          description={error ? translateApiError(t, error) : undefined}
        />
      </div>
    );
  }

  const config = template.config;

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={template.name}
        // A workflow carries a description twice: once as a RESOURCE and once
        // inside its config. The editor writes the config's down onto the
        // resource on every save, so the config's is the source and the
        // resource's is a mirror — which is only ever ahead of it for a
        // workflow created through the API and not edited since.
        subtitle={config.description ?? template.description ?? undefined}
        badges={
          editor.isSaving ? (
            <Badge variant="secondary">{t("workflow.templates.saving")}</Badge>
          ) : null
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setRenaming(true)}>
              <Pencil className="mr-1 size-3.5" aria-hidden />
              {t("common.edit")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => setDeleting(true)}
            >
              <Trash2 className="mr-1 size-3.5" aria-hidden />
              {t("common.delete")}
            </Button>
          </div>
        }
      />

      <TemplateRenameDialog
        template={template}
        open={renaming}
        onOpenChange={setRenaming}
        // The URL carries the name, so a rename has to move the page with it
        // or the next read is a 404 of the workflow that was just saved.
        onRenamed={(next) => navigate(`/workflows/${encodeURIComponent(next)}`, { replace: true })}
      />

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={t("workflow.templates.deleteTitle")}
        description={t("workflow.templates.deleteConfirm", { name: template.name })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        error={del.error}
        onConfirm={async () => {
          await del.mutateAsync({ kind: WORKFLOW_TEMPLATE_KIND, name: template.name });
          navigate("/workflows");
        }}
      />

      {/* A refusal that names no field, from an edit made on the map rather
          than in a dialog — there is no control to put it on and no dialog
          open to hold it. */}
      {editor.error && refusal === null ? (
        <p className="flex items-start gap-2 text-sm text-destructive" role="alert">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {translateApiError(t, editor.error)}
        </p>
      ) : null}

      <TemplateFlow config={config} refusal={refusal} editor={editor} />
    </div>
  );
}
