// frontend/src/pages/WorkflowRunsPage.tsx — spec workflow, FR-045.
// The run list: every delivery this vault is carrying, whichever machine
// advances it. Mirrors ChannelsPage — PageHeader + error / empty / table, with
// the Create action in the header only once there is something to create
// beside, since the empty state carries its own call to action.
//
// The WORKFLOWS these runs are running are a resource kind with their own list
// under `/workflows` and their own sidebar entry (FR-001). This page used to
// carry a button through to them, because the two had been built as one
// surface and a second `/workflows`-prefixed nav entry would have lit up
// beside this page's own on every template URL. Splitting the paths settled
// both.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Route } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { CreateRunDialog } from "@/components/workflow/CreateRunDialog";
import { WorkflowRunsTable } from "@/components/workflow/WorkflowRunsTable";
import { translateApiError } from "@/lib/api/errors";
import { useDeleteRun, useWorkflowRuns } from "@/lib/hooks/useWorkflowRuns";
import type { Run } from "@/lib/api/workflow";

export function WorkflowRunsPage() {
  const { t } = useTranslation();
  const { data: runs, isPending, error } = useWorkflowRuns();
  const del = useDeleteRun();
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<Run | null>(null);
  const hasRuns = (runs ?? []).length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Route}
        title={t("workflow.title")}
        subtitle={t("workflow.subtitle")}
        actions={
          hasRuns ? (
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-1 size-4" /> {t("workflow.create.action")}
            </Button>
          ) : null
        }
      />

      <CreateRunDialog open={showCreate} onOpenChange={setShowCreate} />

      {error ? (
        <Card className="paper-card border-destructive/40">
          <CardHeader>
            <CardTitle className="font-serif text-destructive">
              {t("workflow.loadFailed")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !isPending && !hasRuns ? (
        <EmptyState
          icon={Route}
          title={t("workflow.empty.title")}
          description={t("workflow.empty.body")}
          action={
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-1 size-4" /> {t("workflow.create.action")}
            </Button>
          }
        />
      ) : (
        <WorkflowRunsTable
          runs={runs ?? []}
          isLoading={isPending}
          onDelete={(run) => setDeleting(run)}
        />
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t("workflow.deleteTitle")}
        description={t("workflow.deleteConfirm", { title: deleting?.title ?? "" })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        error={del.error}
        // Closes only on success: a refused delete (a run this machine does not
        // own) stays open with the reason rather than vanishing as if it worked.
        onConfirm={async () => {
          if (deleting === null) return;
          await del.mutateAsync(deleting.id);
          setDeleting(null);
        }}
      />
    </div>
  );
}
