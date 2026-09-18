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
import { Pencil, Trash2, Workflow } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AdhocTaskDialog } from "@/components/workflow/AdhocTaskDialog";
import { RunRelabelDialog } from "@/components/workflow/RunRelabelDialog";
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
  const [relabelling, setRelabelling] = useState(false);

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
        // What the developer says this delivery IS, with what it was started
        // from underneath — the description is theirs and the template ref is
        // provenance, and only one of them is worth the larger line.
        subtitle={run.description ?? run.template_ref}
        badges={
          <div className="flex flex-wrap items-center gap-2">
            <RunStatusBadge status={run.status} />
            {run.owned_here ? null : (
              <Badge variant="secondary">{t("workflow.owner.otherMachine", { machine })}</Badge>
            )}
            {/* What it has spent, as a readout. There is no budget to spend it
                AGAINST: a run is bounded by each task's own attempt ceiling
                (FR-026), and a number of tokens was never a judgement about
                whether the work should continue. */}
            {run.tokens_spent ? (
              <Badge variant="outline">
                {t("workflow.run.tokens", { spent: run.tokens_spent })}
              </Badge>
            ) : null}
          </div>
        }
        // Edit and Delete, and nothing that MOVES the run: its position is
        // folded from the event log (FR-014) and is driven from the task's own
        // page, where what is being decided is in front of the developer
        // (FR-052). Editing the title and description touches none of that
        // (FR-070). Neither button is offered for a run this machine does not
        // advance — it is read-only here, labels included (FR-012).
        actions={
          run.owned_here ? (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setRelabelling(true)}>
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
          ) : null
        }
      />

      <RunRelabelDialog
        runId={run.id}
        title={run.title}
        description={run.description}
        open={relabelling}
        onOpenChange={setRelabelling}
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
