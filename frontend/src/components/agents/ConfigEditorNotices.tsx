// frontend/src/components/agents/ConfigEditorNotices.tsx — spec agent-registry
// "Reject stale config-file writes by fingerprint".
// The two things the config-file pane puts in place of (or above) the file: the
// save the daemon refused because the file changed on disk — a warning banner
// inside the editor (board 2.1.43), the draft kept, with a way to copy it out
// before taking the version on disk — and the allowlisted file the agent has
// not created yet, with the one action that creates it (board 2.1.45; Coffer's
// write creates the file on save).
import { useTranslation } from "react-i18next";
import { FileText, Plus, RotateCcw, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export function ConfigStalePanel({
  name,
  draft,
  onDiscardAndReload,
}: {
  name: string;
  /** The unsaved text, for "Copy my edits". */
  draft: string;
  onDiscardAndReload: () => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      toast.success(t("common.copied"));
    } catch {
      toast.error(t("agents.configTab.copyFailed"));
    }
  };
  return (
    <div
      role="alert"
      className="m-3 flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-warning/30 bg-warning-soft px-3.5 py-2.5"
    >
      <TriangleAlert className="size-[15px] shrink-0 stroke-[1.75] text-warning" aria-hidden />
      <div className="flex min-w-0 flex-1 basis-60 flex-col gap-0.5">
        <p className="text-sm font-semibold text-text">
          {t("agents.configTab.staleTitle", { name })}
        </p>
        <p className="text-xs text-text-muted">{t("agents.configTab.staleBody")}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button size="sm" variant="outline" onClick={() => void copy()}>
          {t("agents.configTab.copyEdits")}
        </Button>
        <Button size="sm" variant="danger" onClick={onDiscardAndReload}>
          <RotateCcw aria-hidden /> {t("agents.configTab.discardAndReload")}
        </Button>
      </div>
    </div>
  );
}

export function ConfigMissingPanel({
  name,
  agentName,
  onCreate,
}: {
  name: string;
  agentName: string;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center">
      <EmptyState
        icon={FileText}
        title={t("agents.configTab.missingTitle", { name })}
        description={t("agents.configTab.missingBody", { agent: agentName })}
        action={
          <Button onClick={onCreate}>
            <Plus aria-hidden /> {t("agents.configTab.create", { name })}
          </Button>
        }
      />
    </div>
  );
}
