// src/components/agents/list/AgentConfigDirReview.tsx — Review changes for moving a connected agent's config directory.
//
// A connected agent carries Coffer's entry and hook in its config directory, so
// pointing it at another folder moves them: the old folder loses both, the new
// one gets both. The daemon has no dry-run diff, so the review is built here
// from the same plan Connect and Disconnect use, and nothing is written until
// Apply. Apply runs in three steps — take Coffer's lines out of the old
// directory, switch the directory (PATCH), write them into the new one — and a
// retry carries on from the step that failed.
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  ChangePreview,
  type ChangeItem,
  type ChangePreviewState,
} from "@/components/change-preview/ChangePreview";
import { planConnect, planDisconnect, type PlanAgent } from "@/lib/agents/connectionPlan";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useAgentConnect, usePatchAgent } from "@/lib/hooks/useAgents";

interface Props {
  row: AgentTypeOut;
  /** The registered agent's uid and what Coffer has written into it now. */
  uid: string;
  parts: CofferConnection["parts"];
  /** The directory the agent moves to. */
  newDir: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Step = "remove" | "move" | "write";
const STEPS: readonly Step[] = ["remove", "move", "write"];

export function AgentConfigDirReview({ row, uid, parts, newDir, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const connect = useAgentConnect(uid);
  const patch = usePatchAgent();
  const [phase, setPhase] = useState<"review" | "applying" | "done">("review");
  const [failedStep, setFailedStep] = useState<Step | null>(null);
  const [error, setError] = useState<string>();
  // The items as reviewed: once the directory changes, the row no longer names the old one.
  const [frozen, setFrozen] = useState<ChangeItem[] | null>(null);
  const completed = useRef<Set<Step>>(new Set());
  const name = agentTypeLabel(row.type);

  const items = useMemo<ChangeItem[]>(() => {
    const opts = {
      placeholders: {
        uid: t("agents.change.placeholder.uid"),
        shim: t("agents.change.placeholder.shim"),
      },
    };
    const oldAgent: PlanAgent = { row, uid, parts };
    // The new directory gets every part, as a fresh Connect would write it.
    const newAgent: PlanAgent = {
      row: { ...row, config_dir: newDir },
      uid,
      parts: parts.map((p) => ({ ...p, installed: false })),
    };
    return [
      ...planDisconnect([oldAgent], opts).map((i) => ({ ...i, id: `old:${i.id}` })),
      ...planConnect([newAgent], opts).map((i) => ({ ...i, id: `new:${i.id}` })),
    ];
  }, [row, uid, parts, newDir, t]);

  const statusOf = (item: ChangeItem): ChangeItem["status"] => {
    if (phase === "review") return undefined;
    const step: Step = item.id.startsWith("old:") ? "remove" : "write";
    if (completed.current.has(step)) return "applied";
    if (failedStep === step || (failedStep === "move" && step === "write")) return "failed";
    return phase === "applying" ? "applying" : "pending";
  };
  const shown = (frozen ?? items).map((item) => {
    const status = statusOf(item);
    return status ? { ...item, status, error: status === "failed" ? error : undefined } : item;
  });

  const run = async () => {
    setFrozen((prev) => prev ?? items);
    setPhase("applying");
    setFailedStep(null);
    setError(undefined);
    for (const step of STEPS) {
      if (completed.current.has(step)) continue;
      try {
        if (step === "remove") await connect.mutateAsync(false);
        else if (step === "move") await patch.mutateAsync({ uid, body: { config_dir: newDir } });
        else await connect.mutateAsync(true);
        completed.current.add(step);
      } catch (e) {
        setFailedStep(step);
        setError(translateApiError(t, e));
        setPhase("done");
        return;
      }
    }
    setPhase("done");
  };

  const state: ChangePreviewState =
    phase === "applying"
      ? "applying"
      : phase === "done"
        ? failedStep
          ? "failed"
          : "applied"
        : "ready";

  return (
    <ChangePreview
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setPhase("review");
          setFailedStep(null);
          setFrozen(null);
          completed.current = new Set();
        }
        onOpenChange(next);
      }}
      title={t("agents.change.title")}
      subtitle={t("agents.configDirDialog.reviewSubtitle", {
        name,
        dir: abbreviateHomePath(newDir),
      })}
      state={state}
      items={shown}
      summaries={[{ agentType: row.type, text: t("agents.configDirDialog.reviewSummary") }]}
      onApply={() => void run()}
      onRetry={() => void run()}
      activityHref="/activity"
    />
  );
}
