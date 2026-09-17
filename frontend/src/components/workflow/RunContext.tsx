// frontend/src/components/workflow/RunContext.tsx
// One table for everything the run is made of: what it READS (FR-032) and
// what it WROTE (FR-041).
//
// These were two tabs, because they come from two routes. That is a fact about
// the API, not about the delivery — the developer's question is "what is in
// this run", and the answer is one list whose rows differ by ORIGIN. Search
// and the origin filter now run over both at once, which is the actual gain:
// "where did td.md come from" used to mean guessing which tab to look in.
//
// Nothing here advances the run, which is why this tab is allowed on the run's
// page at all while Retry and Skip are not (FR-052). Mounting a PRD changes
// what every task that opens afterwards is told about; it does not move the
// delivery. Promotion copies files out and leaves the run untouched.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderUp, Package, Plus } from "lucide-react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRemoveWorkflowInput, useWorkflowInputs } from "@/lib/hooks/useWorkflowInputs";
import { useWorkflowArtifacts } from "@/lib/hooks/useWorkflowRun";
import { buildContextRows, type ContextRow } from "@/lib/workflow/contextRows";
import { PromoteArtifactsDialog } from "./PromoteArtifactsDialog";
import { RunInputDialog } from "./RunInputDialog";
import { useRunContextColumns } from "./RunContextColumns";

/** What unmounting costs, which differs by kind: an uploaded file's bytes go
 *  with it, a repository's checkout goes but its source does not (FR-058), and
 *  a collection or link was never the run's to begin with. */
const REMOVE_CONFIRM = {
  knowledge: "workflow.inputs.removeConfirm",
  link: "workflow.inputs.removeConfirm",
  file: "workflow.inputs.removeFileConfirm",
  note: "workflow.inputs.removeNoteConfirm",
  repo: "workflow.inputs.removeRepoConfirm",
} as const;

interface Props {
  runId: string;
  /** False when another machine advances this run (FR-012). */
  ownedHere: boolean;
  /** Display name of the owning machine, for the read-only tooltip. */
  machine: string;
  /** False while this tab is not showing, so neither list is fetched. */
  enabled?: boolean;
}

export function RunContext({ runId, ownedHere, machine, enabled = true }: Props) {
  const { t } = useTranslation();
  const inputs = useWorkflowInputs(runId, enabled);
  const artifacts = useWorkflowArtifacts(runId, enabled);
  const remove = useRemoveWorkflowInput(runId);
  const [mounting, setMounting] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [removing, setRemoving] = useState<ContextRow | null>(null);

  const isLoading = inputs.isPending || artifacts.isPending;
  const rows = buildContextRows(inputs.data ?? [], artifacts.data?.items ?? []);
  const hasArtifacts = rows.some((row) => row.origin === "produced");
  const columns = useRunContextColumns({
    runId,
    ownedHere,
    machine,
    removing: remove.isPending,
    onRemove: setRemoving,
  });

  const mountButton = (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={ownedHere ? undefined : "cursor-not-allowed"}>
          <Button size="sm" disabled={!ownedHere} onClick={() => setMounting(true)}>
            <Plus aria-hidden />
            {t("workflow.context.add")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {ownedHere ? t("workflow.context.add") : t("workflow.notThisMachine", { machine })}
      </TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="max-w-3xl text-sm text-muted-foreground">
          {t("workflow.context.description")}
        </p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!hasArtifacts}
            onClick={() => setPromoting(true)}
          >
            <FolderUp aria-hidden />
            {t("workflow.artifacts.promote")}
          </Button>
          {mountButton}
        </div>
      </div>

      {!isLoading && rows.length === 0 ? (
        <EmptyState
          icon={Package}
          title={t("workflow.context.emptyTitle")}
          description={t("workflow.context.emptyBody")}
          action={ownedHere ? mountButton : undefined}
        />
      ) : (
        <DataTable
          rows={rows}
          isLoading={isLoading}
          columns={columns}
          rowKey={(row) => row.id}
          search={{
            accessor: (row) => `${row.name} ${row.where ?? ""} ${row.kind}`,
            placeholder: t("workflow.context.searchPlaceholder"),
          }}
          filters={[
            {
              key: "origin",
              label: t("workflow.context.origin.label"),
              allLabel: t("workflow.context.origin.all"),
              options: [
                { value: "mounted", label: t("workflow.context.origin.added") },
                { value: "produced", label: t("workflow.context.origin.produced") },
              ],
              accessor: (row) => row.origin,
            },
          ]}
          emptyMessage={t("workflow.context.noMatches")}
        />
      )}

      <RunInputDialog runId={runId} open={mounting} onOpenChange={setMounting} />
      <PromoteArtifactsDialog runId={runId} open={promoting} onOpenChange={setPromoting} />

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null);
        }}
        title={t("workflow.inputs.removeTitle")}
        description={t(REMOVE_CONFIRM[removing?.input?.kind ?? "knowledge"], {
          ref: removing?.name ?? "",
        })}
        confirmLabel={t("workflow.inputs.remove")}
        pending={remove.isPending}
        error={remove.error}
        // Closes only on success: a refused removal (a run this machine does
        // not own) stays open with the reason rather than vanishing.
        onConfirm={async () => {
          if (removing?.input == null) return;
          await remove.mutateAsync(removing.input.ref);
          setRemoving(null);
        }}
      />
    </div>
  );
}
