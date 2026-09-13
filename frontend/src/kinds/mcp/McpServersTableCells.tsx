// frontend/src/kinds/mcp/McpServersTableCells.tsx
//
// Per-row cell components + the bulk-action bar for McpServersTable. These live
// here (not inline in the table) because each needs its own hooks/dialog state,
// which can't run inside a column's `cell` map, and to keep McpServersTable.tsx
// under the file-size cap.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { resourcesApi } from "@/lib/api/resources";
import { useMcpServerRunner, useMcpServerStatus } from "@/lib/hooks/useMcpServerStatus";
import { HealthBadge } from "./HealthBadge";
import { McpServerDeleteDialog } from "./McpServerDeleteDialog";

/** Persisted health (last /test probe or most recent invocation), else "—".
 * A stdio server whose launcher is missing on THIS machine says so, with a
 * static hint naming the runner to install — Coffer surfaces the cause, the
 * user installs the software. */
export function ServerHealthCell({ name }: { name: string }) {
  const { t } = useTranslation();
  const { data: status } = useMcpServerStatus(name);
  const { data: runner } = useMcpServerRunner(name);

  if (runner?.missingRunner) {
    return (
      <span className="flex flex-col gap-0.5">
        <span className="text-sm text-amber-600">
          {t("mcp.missingRunner", { runner: runner.missingRunner })}
        </span>
        <span className="text-xs text-muted-foreground">
          {t("mcp.missingRunnerHint", { runner: runner.missingRunner })}
        </span>
      </span>
    );
  }
  return status ? <HealthBadge state={status} /> : <span className="text-muted-foreground">—</span>;
}

/** Per-row reach control, the same three-state ScopeControl the detail header
 *  carries: a server is no longer merely on or off, it can be exposed to a
 *  chosen set of agents, which a Switch cannot say.
 *
 *  `resource.scope` rides the list payload, so the control skips its own
 *  per-resource GET — the list still costs one request, not one per row.
 *
 *  The wrapper stops propagation for the whole control, popover included (a
 *  React portal still bubbles through the React tree), so no click inside it
 *  navigates the row. */
export function ServerStatusCell({ resource }: { resource: ResourceOut }) {
  return (
    <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
      <ScopeControl
        kind={resource.kind}
        name={resource.name}
        enabled={resource.enabled}
        scope={resource.scope ?? null}
      />
    </div>
  );
}

/** Delete action: the shared row delete button + the server's styled confirm. */
export function ServerDeleteCell({ resource }: { resource: ResourceOut }) {
  const { t } = useTranslation();
  const del = useDeleteResource();
  const [open, setOpen] = useState(false);

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <RowDeleteButton
        ariaLabel={t("mcp.table.deleteAria", { name: resource.name })}
        onDelete={() => setOpen(true)}
      />
      <McpServerDeleteDialog
        name={resource.name}
        open={open}
        isPending={del.isPending}
        error={del.error}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) del.reset();
        }}
        onConfirm={() =>
          // Close only on success so a failure leaves the dialog (and error) up.
          del.mutate(
            { kind: resource.kind, name: resource.name },
            { onSuccess: () => setOpen(false) },
          )
        }
      />
    </div>
  );
}

/** Bulk reach + delete over the selected rows; clears selection on done.
 *
 *  The reach control is the SAME three-way choice each row carries, applied to
 *  the whole selection — an Enable/Disable pair here could not say "expose
 *  these to exactly these agents", which is a state the rows can be in. */
export function McpServersBulkActions({
  rows,
  onDone,
}: {
  rows: ResourceOut[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  // allSettled fan-out: one failed row never aborts the rest, and a single
  // summary toast reports "N done / M failed". A single ["resources"]
  // invalidation burst refreshes the table after the batch settles.
  const bulk = useBulkMutate({ invalidate: [["resources"]] });

  return (
    <>
      <BulkReachActions rows={rows} onDone={onDone} />
      <BulkDeleteButton
        title={t("common.delete")}
        description={t("mcp.server.deleteConfirmBody")}
        pending={bulk.isPending}
        onConfirm={async () => {
          // Clear regardless of partial failure; the summary toast reports the
          // outcome, so the bar never stays stuck silently.
          await bulk.run(rows, (r) => resourcesApi.remove(r.kind, r.name));
          onDone();
        }}
      />
    </>
  );
}
