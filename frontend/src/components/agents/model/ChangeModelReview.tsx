// src/components/agents/model/ChangeModelReview.tsx — Review changes for a model change (boards 2.1.62, 2.1.66, 2.1.18).
//
// The shared 1060 ChangePreview over what the daemon says the change writes:
// Claude Code's settings.json, or Codex's config.toml plus Coffer's own model
// list file. The connection test already passed in the form. Apply
// sends the fingerprints the preview read; a file edited since refuses the
// write inside this dialog, with Reload preview.
import { useTranslation } from "react-i18next";
import { RotateCw } from "lucide-react";

import {
  ChangePreview,
  type ChangeItem,
  type ChangePreviewState,
} from "@/components/change-preview/ChangePreview";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import type { ModelSwitchFile } from "@/lib/api/modelSwitch";
import type { ConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";
import { useModelSwitchReview } from "@/lib/hooks/useModelSwitch";
import { displayName } from "@/lib/resourceTitle";

const K = "agents.changeModel.review";

interface Props {
  agent: AgentOut;
  draft: ConnectionDraft;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The change was written and the review is done: close the form too. */
  onApplied: () => void;
}

function toItem(agent: AgentOut, file: ModelSwitchFile, status?: ChangeItem["status"]): ChangeItem {
  return {
    id: file.path,
    agentType: agent.type,
    path: abbreviateHomePath(file.path),
    op: file.op,
    added: file.added,
    removed: file.removed,
    status,
    diff: file.diff.map((l) => ({
      kind: l.kind,
      text: l.text,
      oldNo: l.old_no ?? undefined,
      newNo: l.new_no ?? undefined,
    })),
  };
}

export function ChangeModelReview({ agent, draft, open, onOpenChange, onApplied }: Props) {
  const { t } = useTranslation();
  const r = useModelSwitchReview(draft.request, open);
  const files = r.preview.data?.files ?? [];
  const name = agentTypeLabel(agent.type);
  const target = draft.draftConnObj ? displayName(draft.draftConnObj) : null;

  let state: ChangePreviewState;
  let status: ChangeItem["status"];
  if (r.apply.isPending) [state, status] = ["applying", "applying"];
  else if (r.apply.isSuccess) [state, status] = ["applied", "applied"];
  else if (r.apply.isError && !r.stale) [state, status] = ["failed", "failed"];
  else if (r.preview.isPending) [state, status] = ["computing", undefined];
  else if (files.length === 0) [state, status] = ["empty", undefined];
  else [state, status] = ["ready", undefined];
  const items = files.map((f) => ({
    ...toItem(agent, f, status),
    error: status === "failed" ? translateApiError(t, r.apply.error) : undefined,
  }));

  const catalog = files.some((f) => f.path.endsWith("coffer-model-catalog.json"));
  const summary = target
    ? t(`${K}.summary.provider`, {
        provider: target,
        model: draft.request.model,
      }) + (catalog ? ` ${t(`${K}.summary.catalog`, { agent: name })}` : "")
    : t(`${K}.summary.builtin`, { agent: name });

  const lead = r.stale ? (
    <div role="alert" className="flex items-start gap-3 rounded-lg bg-danger-soft px-3.5 py-3">
      <div className="flex min-w-0 grow flex-col gap-0.5">
        <span className="text-sm font-medium text-danger">
          {t(`${K}.staleTitle`, { file: (files[0]?.path ?? "").split("/").pop() })}
        </span>
        <span className="text-xs text-text-muted">{t(`${K}.staleBody`)}</span>
      </div>
      <Button variant="outline" size="sm" onClick={r.reload}>
        <RotateCw aria-hidden />
        {t(`${K}.reload`)}
      </Button>
    </div>
  ) : r.previewError ? (
    <p role="alert" className="text-xs text-danger">
      {translateApiError(t, r.previewError)}
    </p>
  ) : null;

  return (
    <ChangePreview
      open={open}
      onOpenChange={(next) => {
        if (!next && r.apply.isSuccess) onApplied();
        onOpenChange(next);
        if (!next) r.reset();
      }}
      title={t(`${K}.title`)}
      subtitle={
        target
          ? t(`${K}.subtitle.provider`, { agent: name, provider: target })
          : t(`${K}.subtitle.builtin`, { agent: name })
      }
      state={state}
      items={items}
      summaries={[{ agentType: agent.type, text: summary }]}
      onApply={r.run}
      onRetry={r.run}
      activityHref="/activity"
      note={t(catalog ? `${K}.noteCatalog` : `${K}.note`)}
      lead={lead}
    />
  );
}
