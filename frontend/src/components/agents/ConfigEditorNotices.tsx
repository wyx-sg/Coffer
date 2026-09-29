// frontend/src/components/agents/ConfigEditorNotices.tsx — spec agent-registry
// "Reject stale config-file writes by fingerprint".
// The two panels the config-file pane puts in place of (or above) the file:
// the save the daemon refused because the file changed on disk — the draft is
// kept, with a way to copy it out before taking the version on disk — and the
// allowlisted file the agent has not created yet, with the one action that
// creates it (Coffer's write creates the file on save).
import { useTranslation } from "react-i18next";

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
      className="shrink-0 space-y-2 rounded-md border border-danger bg-danger-soft px-3 py-2"
    >
      <p className="text-sm font-medium text-danger">
        {t("agents.configTab.staleTitle", { name })}
      </p>
      <p className="text-xs text-text-muted">{t("agents.configTab.staleBody")}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => void copy()}>
          {t("agents.configTab.copyEdits")}
        </Button>
        <Button size="sm" variant="outline" onClick={onDiscardAndReload}>
          {t("files.discardAndReload")}
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
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 rounded-md border border-dashed px-6 py-10 text-center">
      <p className="text-md font-semibold text-text">{t("agents.configTab.missingTitle")}</p>
      <p className="max-w-empty text-sm text-text-muted">
        {t("agents.configTab.missingBody", { agent: agentName })}
      </p>
      <Button size="sm" onClick={onCreate}>
        {t("agents.configTab.create", { name })}
      </Button>
    </div>
  );
}
