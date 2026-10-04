// src/components/providers/DeleteProviderDialog.tsx — delete a provider; while something runs on it, review what that changes first.
//
// An unused provider is deleted after a ConfirmDialog (its own secret goes
// with it) and the page returns to the list. A provider in use is NOT blocked:
// Delete opens a review (the 1060 ChangePreview) — "What will happen" for each
// user of the provider (an agent goes back to its own login, speech to text
// turns off, the key is deleted) beside the exact lines
// the daemon removes from each agent's config file — and Delete applies it.
// The lines are the daemon's own dry run of the removal, never drawn here.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound, Mic, type LucideIcon } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { ChangePreview, type ChangePreviewState } from "@/components/change-preview/ChangePreview";
import { Section } from "@/components/Section";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { useDeleteProvider } from "@/lib/hooks/useProviders";
import { isInUse, type ProviderUse } from "@/lib/providers/usedBy";
import { displayName } from "@/lib/resourceTitle";
import { previewItems, useDeletePreview } from "./useDeletePreview";

interface Props {
  open: boolean;
  provider: Provider;
  use: ProviderUse;
  onClose: () => void;
}

interface Consequence {
  key: string;
  lead: React.ReactNode;
  title: string;
  body: React.ReactNode;
}

function Tile({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-item bg-chip text-text-muted">
      <Icon className="size-3.5" aria-hidden />
    </span>
  );
}

/** What deleting the provider does to each thing that runs on it, one line each. */
function useConsequences(provider: Provider, use: ProviderUse, files: Map<string, string>) {
  const { t } = useTranslation();
  const out: Consequence[] = use.agents.map(({ agent }) => {
    const label = agentTypeLabel(agent.type);
    const path = files.get(agent.uid);
    return {
      key: agent.uid,
      lead: <AgentBadge type={agent.type} size="sm" tooltip={false} />,
      title: t("providers.delete.agentTitle", { agent: label }),
      body: path
        ? t("providers.delete.agentBody", { path })
        : t("providers.delete.agentBodyNoFile"),
    };
  });
  if (use.transcribe) {
    out.push({
      key: "transcribe",
      lead: <Tile icon={Mic} />,
      title: t("providers.delete.transcribeTitle"),
      body: t("providers.delete.transcribeBody"),
    });
  }
  if (provider.secret_ref) {
    out.push({
      key: "key",
      lead: <Tile icon={KeyRound} />,
      title: t("providers.delete.keyTitle"),
      body: <span className="font-mono">{provider.secret_ref}</span>,
    });
  }
  return out;
}

function ConsequenceList({ rows }: { rows: Consequence[] }) {
  const { t } = useTranslation();
  return (
    <Section title={t("changePreview.whatWillHappen")} gap="snug">
      <ul className="flex flex-col divide-y divide-border-subtle">
        {rows.map((r) => (
          <li key={r.key} className="flex items-start gap-2.5 py-2 first:pt-0">
            {r.lead}
            <span className="flex min-w-0 flex-col">
              <span className="text-sm font-label text-text">{r.title}</span>
              <span className="text-xs text-text-muted">{r.body}</span>
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function DeleteProviderDialog({ open, provider, use, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteProvider();
  const name = displayName(provider);
  const inUse = isInUse(use);
  const preview = useDeletePreview(provider.uid, open && inUse);
  const items = previewItems(preview.data);
  const [phase, setPhase] = useState<"review" | "applying" | "failed">("review");

  useEffect(() => {
    if (open) {
      setPhase("review");
      del.reset();
    }
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const pathOfAgent = new Map<string, string>(
    (preview.data?.agents ?? []).flatMap((a) =>
      a.files[0] ? [[a.agent_uid, abbreviateHomePath(a.files[0].path)] as const] : [],
    ),
  );
  const consequences = useConsequences(provider, use, pathOfAgent);

  const remove = () =>
    del.mutate(provider.uid, {
      onSuccess: () => {
        onClose();
        navigate("/model-providers");
      },
      onError: () => setPhase("failed"),
    });

  // Nothing of an agent's file changes (only Coffer's engine or speech to
  // text ran on it, or the agent is switched off): a plain confirmation that
  // still names every consequence.
  if (!inUse || (!preview.isPending && items.length === 0)) {
    return (
      <ConfirmDialog
        open={open}
        onOpenChange={(o) => !o && onClose()}
        title={t("providers.delete.title", { name })}
        description={
          provider.secret_ref
            ? t("providers.delete.confirmWithSecret", { name, ref: provider.secret_ref })
            : t("providers.delete.confirm", { name })
        }
        confirmLabel={t("providers.actions.delete")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDelete", { name })}
        pending={del.isPending}
        error={del.error}
        onConfirm={remove}
      >
        {inUse ? (
          <ul className="flex flex-col gap-1.5">
            {consequences
              .filter((c) => c.key !== "key")
              .map((c) => (
                <li key={c.key} className="text-xs text-text-muted">
                  <span className="font-label text-text">{c.title}.</span> {c.body}
                </li>
              ))}
          </ul>
        ) : null}
      </ConfirmDialog>
    );
  }

  const state: ChangePreviewState = preview.isPending
    ? "computing"
    : phase === "applying" || del.isPending
      ? "applying"
      : phase === "failed"
        ? "failed"
        : "ready";
  const shown = items.map((item) =>
    state === "applying"
      ? { ...item, status: "applying" as const }
      : state === "failed"
        ? {
            ...item,
            status: "failed" as const,
            error: del.error ? translateApiError(t, del.error) : undefined,
          }
        : item,
  );

  return (
    <ChangePreview
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={t("providers.delete.title", { name })}
      subtitle={t("providers.delete.reviewSubtitle", { count: items.length })}
      state={state}
      items={shown}
      lead={<ConsequenceList rows={consequences} />}
      applyLabel={t("providers.actions.deleteShort")}
      applyDestructive
      note={t("providers.delete.note")}
      onApply={() => {
        setPhase("applying");
        remove();
      }}
      onRetry={() => {
        setPhase("applying");
        remove();
      }}
    />
  );
}
