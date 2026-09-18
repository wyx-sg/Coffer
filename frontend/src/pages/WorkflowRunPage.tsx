// frontend/src/pages/WorkflowRunPage.tsx — one run (spec workflow, FR-045).
//
// THIS PAGE IS A MAP, AND A MAP HAS NO CONTROLS (FR-052). It says where the
// delivery is, what it has produced and what it is reading, and offers nothing
// that advances or alters it. Start, pause, abort, retry, skip, complete,
// feedback and Approve / Reject were all here once; every one of them now
// lives on the conversation of the task it belongs to, where the thing being
// decided is in front of the developer. A run has no conversation of its own
// (FR-030), so there is no thread here either — clicking a node opens its.
//
// Two tabs, and the tab lives in the URL (`?tab=context`) so a link can land
// on one and a reload comes back:
//   • STAGES — the shape of the work and where it got to.
//   • CONTEXT — what the run reads AND what it has produced, in one table.
//     Editable (FR-050): mounting a PRD changes what every later task is told
//     about, not where the delivery is, so it is not a control this page is
//     forbidden to have.
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trash2, Workflow } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AdhocTaskDialog } from "@/components/workflow/AdhocTaskDialog";
import { RunContext } from "@/components/workflow/RunContext";
import { RunStages } from "@/components/workflow/RunStages";
import { RunStatusBadge } from "@/components/workflow/WorkflowStatusBadge";
import { translateApiError } from "@/lib/api/errors";
import { useWorkflowRun } from "@/lib/hooks/useWorkflowRun";
import { useDeleteRun, useMachineLabel } from "@/lib/hooks/useWorkflowRuns";

const TABS = ["flow", "context"] as const;
type RunTab = (typeof TABS)[number];

function isRunTab(value: string | null): value is RunTab {
  return (TABS as readonly string[]).includes(value ?? "");
}

export function WorkflowRunPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { runId = "" } = useParams<{ runId: string }>();
  const [params, setParams] = useSearchParams();
  const { data: detail, isPending, error } = useWorkflowRun(runId);
  const machineLabel = useMachineLabel();
  const del = useDeleteRun();
  const [adhocStage, setAdhocStage] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const requested = params.get("tab");
  const tab: RunTab = isRunTab(requested) ? requested : "flow";
  const setTab = (next: string) => {
    const search = new URLSearchParams(params);
    if (next === "flow") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
  };

  const back = { to: "/runs", label: t("workflow.backToRuns") };

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-64" />} />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={runId} />
        <EmptyState
          icon={Workflow}
          title={t("workflow.notFound")}
          description={error ? translateApiError(t, error) : undefined}
        />
      </div>
    );
  }

  const { run } = detail;
  const machine = machineLabel(run.machine_id);

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={run.title}
        subtitle={run.template_ref}
        badges={
          <div className="flex flex-wrap items-center gap-2">
            <RunStatusBadge status={run.status} />
            {run.owned_here ? null : (
              <Badge variant="secondary">{t("workflow.owner.otherMachine", { machine })}</Badge>
            )}
            {run.token_budget ? (
              <Badge variant="outline">
                {t("workflow.run.tokens", {
                  spent: run.tokens_spent ?? 0,
                  budget: run.token_budget,
                })}
              </Badge>
            ) : null}
          </div>
        }
        // Delete and nothing else. A run is operational state driven by
        // commands and rebuilt from its event log (FR-014) — there is no edit
        // of a run's row anywhere, and the title it was created with is the
        // title every one of its events was attributed under.
        actions={
          <Button
            variant="outline"
            size="sm"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => setDeleting(true)}
          >
            <Trash2 className="mr-1 size-3.5" aria-hidden />
            {t("common.delete")}
          </Button>
        }
      />

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={t("workflow.deleteTitle")}
        description={t("workflow.deleteConfirm", { title: run.title })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        error={del.error}
        onConfirm={async () => {
          await del.mutateAsync(run.id);
          navigate("/runs");
        }}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="flow">{t("workflow.tabs.flow")}</TabsTrigger>
          <TabsTrigger value="context">{t("workflow.tabs.context")}</TabsTrigger>
        </TabsList>
        <TabsContent value="flow" className="pt-4">
          <RunStages detail={detail} machine={machine} onAddTask={setAdhocStage} />
        </TabsContent>
        <TabsContent value="context" className="pt-4">
          <RunContext
            runId={run.id}
            ownedHere={run.owned_here}
            machine={machine}
            enabled={tab === "context"}
          />
        </TabsContent>
      </Tabs>

      {/* Adding an unplanned task does not advance the run — it opens a new
          conversation, and the developer lands in it. */}
      <AdhocTaskDialog
        runId={run.id}
        version={run.version}
        stageKey={adhocStage}
        onClose={() => setAdhocStage(null)}
        onAdded={(nodeKey) => navigate(`/runs/${run.id}/nodes/${encodeURIComponent(nodeKey)}`)}
      />
    </div>
  );
}
