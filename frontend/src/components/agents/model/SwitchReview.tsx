// src/components/agents/model/SwitchReview.tsx — the Model tab's "Review the switch" pane: what Coffer will write, Discard and Confirm switch, and the stale-file refusal.
import { useTranslation } from "react-i18next";
import { RotateCw } from "lucide-react";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { OpChip } from "@/components/change-preview/OpChip";
import { Button } from "@/components/ui/button";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import type { ConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";
import { planSwitch, targetPath } from "./switchPlan";

interface Props {
  agent: AgentOut;
  draft: ConnectionDraft;
}

const PANE = "flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-surface-raised p-4";

export function SwitchReview({ agent, draft: c }: Props) {
  const { t } = useTranslation();

  if (!c.dirty) {
    return (
      <section aria-label={t("agents.modelTab.review.title")} className={PANE}>
        <span className="text-sm font-semibold text-text">
          {t("agents.modelTab.review.nothingTitle")}
        </span>
        <p className="text-xs leading-relaxed text-text-muted">
          {t(
            c.draftIsBuiltin
              ? "agents.modelTab.review.nothingBuiltin"
              : "agents.modelTab.review.nothingConnection",
            { path: targetPath(agent) },
          )}
        </p>
      </section>
    );
  }

  const plan = planSwitch(agent, c, t);
  const added = plan.lines.filter((l) => l.kind === "add").length;
  const removed = plan.lines.length - added;
  const footnote = c.draftIsBuiltin
    ? t("agents.modelTab.review.footnoteBuiltin")
    : t(`agents.modelTab.review.footnote.${agent.type}`);

  return (
    <section aria-label={t("agents.modelTab.review.title")} className={PANE}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-text">{t("agents.modelTab.review.title")}</span>
        <span className="ml-auto inline-flex items-center gap-1.5">
          <OpChip op="modify" />
          <span className="text-xs text-text-muted">
            {t("agents.modelTab.review.fileCount", { count: 1 })}
          </span>
        </span>
      </div>

      {c.stale ? (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-lg border border-border bg-danger-soft p-3"
        >
          <span className="text-sm font-semibold text-danger">
            {t("agents.modelTab.review.staleTitle", { file: plan.path.split("/").pop() })}
          </span>
          <p className="text-xs leading-relaxed text-text-muted">
            {t("agents.modelTab.review.staleBody")}
          </p>
          <Button variant="outline" size="sm" className="self-start" onClick={c.reload}>
            <RotateCw aria-hidden />
            {t("agents.modelTab.review.reload")}
          </Button>
        </div>
      ) : null}

      <FileDiff
        item={{
          id: "model-switch",
          agentType: agent.type,
          path: plan.path,
          op: "modify",
          added,
          removed,
          diff: plan.lines,
        }}
      />

      <p className="text-xs leading-relaxed text-text-muted">
        {footnote}
        {!c.draftIsBuiltin && c.effortLevels.length === 0
          ? ` ${t("agents.modelTab.review.effortLeftOut")}`
          : null}
      </p>

      {c.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, c.error)}
        </p>
      ) : null}
      {!c.draftIsBuiltin && !c.testResult?.ok ? (
        <p className="text-xs text-text-subtle">{t("agents.modelTab.review.testFirst")}</p>
      ) : null}

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" onClick={c.discard} disabled={c.busy}>
          {t("agents.modelTab.review.discard")}
        </Button>
        <Button onClick={c.confirm} disabled={!c.canConfirm || c.busy}>
          {c.busy ? t("common.saving") : t("agents.modelTab.review.confirm")}
        </Button>
      </div>
    </section>
  );
}
