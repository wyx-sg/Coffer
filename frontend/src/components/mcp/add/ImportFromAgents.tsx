// frontend/src/components/mcp/add/ImportFromAgents.tsx — "Review import"
// (board 4.1.18 Mcp-ImportAgents; spec agent-registry "Plan an import of
// agents' direct MCP entries" / "Apply an import of agents' direct MCP entries").
//
// Every direct MCP entry in the agents' own config files, as the daemon plans
// importing them, shown in the shared change preview before anything is
// written: the servers found (ticked; a server two agents share merges into
// one, a duplicate of a server Coffer has only loses its entry), what will
// happen, and each agent file's diff. Import applies the same plan; the daemon
// recomputes it first, so nothing the file no longer holds is written.
import { useMemo, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { ChangePreview, type ChangePreviewState } from "@/components/change-preview/ChangePreview";
import type { useToast } from "@/components/ui/toast";
import type { McpImportApplyResult, McpImportEntryIn } from "@/lib/api/mcpImport";
import { useAgentDirectMcpEntries } from "@/lib/hooks/useAgentDirectMcpEntries";
import { useApplyMcpImport, useMcpImportPlan } from "@/lib/hooks/useMcpAddFlow";
import { addedCount, entryKey, planItems, planSummaries, toEntryIn } from "./importPlanItems";
import { ImportServersFound } from "./ImportServersFound";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once the import was applied, with every entry's outcome. */
  onDone: (result: McpImportApplyResult) => void;
}

export function ImportFromAgents({ open, onOpenChange, onDone }: Props) {
  const { t } = useTranslation();
  const { groups, isLoading } = useAgentDirectMcpEntries();
  const [unticked, setUnticked] = useState<Set<string>>(new Set());
  const apply = useApplyMcpImport();

  const offered: McpImportEntryIn[] = useMemo(
    () =>
      groups.flatMap((g) =>
        [...g.entries, ...g.duplicates].map((entry) => toEntryIn(g.agent.uid, entry)),
      ),
    [groups],
  );
  const everything = useMcpImportPlan(offered, open && !isLoading);
  // A name the daemon cannot register is never sent: the import would only refuse it.
  const unusable = new Set(
    (everything.data?.servers ?? [])
      .filter((s) => !s.name_usable)
      .flatMap((s) => s.entries.map(entryKey)),
  );
  const chosen = offered.filter((e) => !unticked.has(entryKey(e)) && !unusable.has(entryKey(e)));
  const plan = useMcpImportPlan(chosen, open && !isLoading && everything.isSuccess);

  const toggle = (keys: string[], on: boolean) =>
    setUnticked((prev) => {
      const next = new Set(prev);
      for (const k of keys) {
        if (on) next.delete(k);
        else next.add(k);
      }
      return next;
    });

  const items = plan.data && chosen.length > 0 ? planItems(plan.data, t) : [];
  const summaries = plan.data && chosen.length > 0 ? planSummaries(plan.data, t) : [];
  const loading =
    isLoading || everything.isPending || (chosen.length > 0 && plan.isPending && !plan.data);
  const state: ChangePreviewState = apply.isPending ? "applying" : loading ? "computing" : "ready";
  const count = chosen.length > 0 ? addedCount(plan.data) : 0;

  const run = () =>
    apply.mutate(chosen, {
      onSuccess: (result) => onDone(result),
    });

  return (
    <ChangePreview
      open={open}
      onOpenChange={onOpenChange}
      title={t("mcp.import.title")}
      subtitle={t("mcp.import.sub")}
      state={state}
      items={items}
      summaries={summaries}
      onApply={run}
      applyLabel={
        count > 0
          ? t("mcp.import.importN", { count })
          : t("changePreview.applyCount", { count: items.length })
      }
      note={t("mcp.import.footNote")}
      diffNote={t("mcp.import.diffNote")}
      lead={
        <ImportServersFound
          plan={everything.data}
          groups={groups}
          chosen={new Set(chosen.map(entryKey))}
          error={everything.error ?? plan.error ?? apply.error}
          onToggle={toggle}
          busy={apply.isPending}
        />
      }
    />
  );
}

/** Say how the import went: every entry imported, or which did not and why. */
export function toastImport(
  toast: ReturnType<typeof useToast>["toast"],
  t: TFunction,
  result: McpImportApplyResult,
) {
  const failed = result.entries.filter((e) => e.outcome === "failed");
  if (failed.length === 0) {
    toast.success(t("mcp.import.done", { count: result.servers_added.length }));
    return;
  }
  toast.error(
    t("mcp.import.partial", {
      done: result.entries.length - failed.length,
      total: result.entries.length,
      names: failed.map((f) => f.name).join(", "),
      reason: failed[0].message ?? "",
    }),
  );
}
