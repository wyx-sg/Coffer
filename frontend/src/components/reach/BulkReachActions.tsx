// frontend/src/components/reach/BulkReachActions.tsx
//
// The reach choice over a whole table selection (Foundations-Reach "Bulk
// reach"): a "Reach" button in the selection bar opening a 340-wide popover
// with the same three modes as one resource — Off, All agents, Chosen agents —
// which apply to every selected item. Under Chosen agents each agent has a
// tri-state box over the selection and a count ("2 of 3"; a changed row reads
// "2 of 3 → 3 of 3").
//
// A bulk write is a NEW INTENT, not an edit of one row's value, so — unlike
// the single control — it WAITS FOR APPLY: nothing is picked at first, the
// footer says what will change, and Cancel drops every staged box.
//
// Every item is attempted; one failure never aborts the rest. A partial
// failure is written inside the popover (an error block naming the items and
// why, with Retry for just those) — never a toast. Success closes the popover,
// toasts the count once and clears the selection.
import { useId, useState } from "react";
import type { QueryKey } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { BulkAgentRows } from "@/components/reach/BulkAgentRows";
import { ReachButton } from "@/components/reach/ReachButton";
import { ReachChoice } from "@/components/reach/ReachChoice";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useToast } from "@/components/ui/toast";
import { sortAgents } from "@/components/agent/agentOrder";
import { useAgents } from "@/lib/hooks/useAgents";
import {
  countAfter,
  countNow,
  nextEdit,
  planRow,
  type AgentEdit,
  type BulkPlan,
  type BulkRow,
} from "@/lib/reach/bulkReach";
import { pickableAgents, reachModeName, type ReachMode } from "@/lib/reach/reachState";
import { useBulkApply, type BulkFailure, type BulkWrite } from "@/lib/reach/useBulkApply";

interface Props {
  rows: BulkRow[];
  /** Popover title; defaults to "Reach for N selected" (a page can say "3 skills"). */
  title?: string;
  /** The kind's own list key, refreshed alongside the generic ones. */
  invalidate?: QueryKey[];
  /** Clears the table selection once every item has been written. */
  onDone: () => void;
}

const MODES: ReachMode[] = ["disabled", "everywhere", "restricted"];

export function BulkReachActions({ rows, title, invalidate = [], onDone }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: agentsData } = useAgents();
  const { apply, isPending } = useBulkApply(invalidate);
  const group = useId();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ReachMode | null>(null);
  const [edits, setEdits] = useState<Record<string, AgentEdit>>({});
  const [failed, setFailed] = useState<{ ok: number; failures: BulkFailure[] } | null>(null);

  const agents = sortAgents(pickableAgents(agentsData));
  const uids = agents.map((a) => a.uid);
  const plan: BulkPlan = { mode, edits };
  const writes: BulkWrite[] = rows.flatMap((row) => {
    const value = planRow(row, plan, uids);
    return value ? [{ row, value }] : [];
  });
  const changed = Object.values(edits).filter((e) => e !== "orig").length;

  const reset = () => {
    setMode(null);
    setEdits({});
    setFailed(null);
  };
  const close = () => {
    setOpen(false);
    reset();
  };

  const run = async (todo: BulkWrite[]) => {
    const result = await apply(todo);
    if (result.failures.length === 0) {
      toast.success(t("common.bulk.summary.allOk", { count: todo.length }));
      close();
      onDone();
      return;
    }
    setFailed({ ok: result.ok, failures: result.failures });
  };

  const cycle = (uid: string) =>
    setEdits((prev) => ({
      ...prev,
      [uid]: nextEdit(prev[uid] ?? "orig", countNow(rows, uid), rows.length),
    }));

  const summary = (() => {
    if (writes.length === 0) return t("scope.bulkNothing");
    if (mode === "disabled") return t("scope.bulkOff", { count: writes.length });
    if (mode === "everywhere") return t("scope.bulkAll", { count: writes.length });
    const detail = changed === 1 ? Object.keys(edits).find((u) => edits[u] !== "orig") : undefined;
    const agent = agents.find((a) => a.uid === detail);
    const delta = agent ? countAfter(rows, plan, uids, agent.uid) - countNow(rows, agent.uid) : 0;
    const head = t("scope.bulkChanges", { count: changed });
    const willOff = writes.filter((w) => !w.value.enabled).length;
    const parts = [head];
    if (agent && delta !== 0) {
      parts.push(
        t(delta > 0 ? "scope.bulkGets" : "scope.bulkLoses", {
          name: agent.name,
          count: Math.abs(delta),
        }),
      );
    }
    if (willOff > 0) parts.push(t("scope.bulkWillOff", { count: willOff }));
    return parts.join(" · ");
  })();

  const subs: Record<ReachMode, string> = {
    disabled: t("scope.disabledSub"),
    everywhere: t("scope.everywhereSub"),
    restricted: t("scope.restrictedSub"),
  };
  const failedNames = failed?.failures.map((f) => f.write.row.name ?? f.write.row.uid).join(", ");

  return (
    <div className="inline-flex" data-testid="bulk-reach-control">
      <Popover open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <PopoverTrigger asChild>
          <ReachButton
            live={null}
            label={t("scope.setReach")}
            chosen={[]}
            disabled={isPending}
            aria-label={t("scope.bulkReach")}
          />
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="flex max-h-[480px] w-[340px] flex-col gap-2.5 p-3 text-text"
        >
          <p className="text-xs font-semibold text-text">
            {title ?? t("scope.bulkTitle", { count: rows.length })}
          </p>
          <div
            role="radiogroup"
            aria-label={t("scope.choicesLabel")}
            className="border-b border-border-subtle pb-2.5"
          >
            {MODES.map((value) => (
              <ReachChoice
                key={value}
                group={group}
                checked={mode === value}
                disabled={isPending}
                text={reachModeName(t, value)}
                sub={subs[value]}
                onPick={() => setMode(value)}
              />
            ))}
          </div>

          <BulkAgentRows
            agents={agents}
            total={rows.length}
            edits={edits}
            now={(uid) => countNow(rows, uid)}
            after={(uid) => countAfter(rows, plan, uids, uid)}
            active={mode === "restricted"}
            disabled={isPending}
            onCycle={cycle}
          />

          {failed ? (
            <div
              role="alert"
              className="flex flex-col gap-0.5 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger"
            >
              <span className="font-semibold">
                {failed.ok > 0
                  ? t("scope.bulkPartial", {
                      ok: failed.ok,
                      total: failed.ok + failed.failures.length,
                    })
                  : t("scope.bulkNone")}
              </span>
              <span>
                {t("scope.bulkPartialBody", {
                  names: failedNames,
                  reason: failed.failures[0]?.message,
                })}
              </span>
            </div>
          ) : null}

          <div className="flex min-h-control-sm items-center justify-between gap-3 border-t border-border-subtle pt-2">
            <span className="min-w-0 text-xs text-text-muted" data-testid="reach-summary">
              {failed ? "" : summary}
            </span>
            <span className="flex shrink-0 gap-1.5">
              <Button type="button" variant="ghost" size="sm" onClick={close}>
                {failed ? t("common.close") : t("common.cancel")}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={isPending || (failed === null && writes.length === 0)}
                loading={isPending}
                onClick={() => void run(failed ? failed.failures.map((f) => f.write) : writes)}
              >
                {failed ? t("common.retry") : t("scope.apply")}
              </Button>
            </span>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
