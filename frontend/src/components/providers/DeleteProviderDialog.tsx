// src/components/providers/DeleteProviderDialog.tsx — delete a provider, or say what still runs on it.
//
// While anything uses the provider — an agent switched to it (the Used-by
// rule), Coffer's engine or speech to text — the delete is blocked: the dialog
// names each user with a link to where it is changed, and Delete stays
// disabled. An unused provider is deleted after a ConfirmDialog (its owned
// secret goes with it), and the page returns to the list.
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Cpu, Mic } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import type { Provider } from "@/lib/api/providers";
import { useDeleteProvider } from "@/lib/hooks/useProviders";
import { isInUse, type ProviderUse } from "@/lib/providers/usedBy";
import { displayName } from "@/lib/resourceTitle";
import { useOpenSettings } from "@/lib/settingsModal";

interface Props {
  open: boolean;
  provider: Provider;
  use: ProviderUse;
  onClose: () => void;
}

const ROW =
  "flex items-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm text-text no-underline hover:bg-surface-hover outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";

export function DeleteProviderDialog({ open, provider, use, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteProvider();
  const openSettings = useOpenSettings();
  const name = displayName(provider);

  if (!isInUse(use)) {
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
        errorTitle={t("common.couldntDelete", { name: name })}
        pending={del.isPending}
        onConfirm={() =>
          del.mutate(provider.uid, {
            onSuccess: () => {
              onClose();
              navigate("/model-providers");
            },
          })
        }
      />
    );
  }

  const settingsRow = (key: string, icon: typeof Cpu, label: string) => {
    const Icon = icon;
    return (
      <button
        key={key}
        type="button"
        className={ROW}
        onClick={() => {
          onClose();
          openSettings("general");
        }}
      >
        <span className="inline-flex size-6 items-center justify-center rounded-item bg-chip text-text-muted">
          <Icon className="size-3.5" aria-hidden />
        </span>
        <span className="flex-1">{label}</span>
        <span className="text-xs text-text-muted">{t("providers.usedBy.changeInSettings")}</span>
        <ChevronRight className="size-4 text-text-subtle" aria-hidden />
      </button>
    );
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("providers.delete.title", { name })}</DialogTitle>
          <DialogDescription>{t("providers.delete.blocked", { name })}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col">
          {use.agents.map(({ agent }) => {
            const label = agentTypeLabel(agent.type);
            return (
              <Link key={agent.uid} to={agentTabPath(agent.type, "model")} className={ROW}>
                <AgentBadge type={agent.type} size="md" tooltip={false} />
                <span className="flex-1">{label}</span>
                <span className="text-xs text-text-muted">
                  {t("providers.usedBy.changeInAgent", { agent: label })}
                </span>
                <ChevronRight className="size-4 text-text-subtle" aria-hidden />
              </Link>
            );
          })}
          {use.engine ? settingsRow("engine", Cpu, t("providers.usedBy.engine")) : null}
          {use.transcribe ? settingsRow("transcribe", Mic, t("providers.usedBy.transcribe")) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant="destructive" disabled>
            {t("providers.actions.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
