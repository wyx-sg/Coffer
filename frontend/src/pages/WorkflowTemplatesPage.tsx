// frontend/src/pages/WorkflowTemplatesPage.tsx — spec workflow, FR-054.
// The workflows: the shapes of work this vault knows how to run, as opposed to
// the runs carrying one out. This is the resource kind's list page (FR-001) and
// sits with the other kinds under Resources; a RUN of one is operational state
// and lives under `/runs` with the agents.
//
// "Template" is this file's word and the API's; the UI says "workflow", which
// is what the resource is called everywhere else in the vault.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Workflow } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { TemplateCreateDialog } from "@/components/workflow/TemplateCreateDialog";
import { TemplatesTable } from "@/components/workflow/TemplatesTable";
import { translateApiError } from "@/lib/api/errors";
import {
  useDeleteWorkflowTemplate,
  useWorkflowTemplates,
  type WorkflowTemplate,
} from "@/lib/hooks/useWorkflowTemplates";

export function WorkflowTemplatesPage() {
  const { t } = useTranslation();
  const { templates, isPending, error } = useWorkflowTemplates();
  const del = useDeleteWorkflowTemplate();
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<WorkflowTemplate | null>(null);
  const hasTemplates = templates.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Workflow}
        title={t("workflow.templates.title")}
        subtitle={t("workflow.templates.subtitle")}
        actions={
          hasTemplates ? (
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-1 size-4" /> {t("workflow.templates.create")}
            </Button>
          ) : null
        }
      />

      <TemplateCreateDialog open={showCreate} onOpenChange={setShowCreate} />

      {error ? (
        <Card className="paper-card border-destructive/40">
          <CardHeader>
            <CardTitle className="font-serif text-destructive">
              {t("workflow.templates.loadFailed")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !isPending && !hasTemplates ? (
        <EmptyState
          icon={Workflow}
          title={t("workflow.templates.emptyTitle")}
          description={t("workflow.templates.emptyBody")}
          action={
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-1 size-4" /> {t("workflow.templates.create")}
            </Button>
          }
        />
      ) : (
        <TemplatesTable
          templates={templates}
          isLoading={isPending}
          onDelete={(template) => setDeleting(template)}
        />
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t("workflow.templates.deleteTitle")}
        description={t("workflow.templates.deleteConfirm", { name: deleting?.name ?? "" })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        error={del.error}
        // Closes only on success: a refused delete stays open with its reason
        // rather than vanishing as if it had worked.
        onConfirm={async () => {
          if (deleting === null) return;
          await del.mutateAsync(deleting.uid);
          setDeleting(null);
        }}
      />
    </div>
  );
}
