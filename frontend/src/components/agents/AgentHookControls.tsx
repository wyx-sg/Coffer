// frontend/src/components/agents/AgentHookControls.tsx — slice 6 (rules injection).
// Session-start hook install control, mirroring AgentMcpControls: an "Inject
// Coffer rules at session start" button when not installed and an "Uninstall"
// button once installed, with pending state and inline error surfacing. When the
// agent type has no hook support the status read fails with a 422
// HOOK_INSTALL_UNSUPPORTED — we present a disabled control + explanatory text so
// a hook-less agent type never shows a broken button.
import { useTranslation } from "react-i18next";
import { ScrollText, Unplug } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useAgentHookInstall, useAgentHookStatus } from "@/lib/hooks/useAgents";

/**
 * Session-start hook control. Reads install status; when the agent type doesn't
 * support hooks (422 `HOOK_INSTALL_UNSUPPORTED`), renders a disabled button with
 * an explanatory line instead of a clickable action that would always fail.
 */
export function AgentHookButton({ name }: { name: string }) {
  const { t } = useTranslation();
  const status = useAgentHookStatus(name);
  const mutate = useAgentHookInstall(name);

  const unsupported =
    status.error instanceof ApiError && status.error.code === "HOOK_INSTALL_UNSUPPORTED";

  if (unsupported) {
    return (
      <div className="flex flex-col items-end gap-1.5">
        <Button variant="outline" size="sm" disabled>
          <ScrollText className="mr-1.5 size-3.5" />
          {t("agents.hook.install")}
        </Button>
        <p className="max-w-xs text-right text-xs text-muted-foreground">
          {t("agents.hook.unsupported")}
        </p>
      </div>
    );
  }

  const installed = status.data?.installed ?? false;

  return (
    <div className="flex flex-col items-end gap-1.5">
      {installed ? (
        <Button
          variant="outline"
          size="sm"
          disabled={mutate.isPending}
          onClick={() => mutate.mutate(false)}
        >
          <Unplug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.hook.uninstall")}
        </Button>
      ) : (
        <Button
          size="sm"
          disabled={mutate.isPending || status.isPending}
          onClick={() => mutate.mutate(true)}
        >
          <ScrollText className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.hook.install")}
        </Button>
      )}
      <p className="max-w-xs text-right text-xs text-muted-foreground">{t("agents.hook.help")}</p>
      {mutate.error ? (
        <p className="max-w-xs text-right text-xs text-destructive">
          {translateApiError(t, mutate.error)}
        </p>
      ) : null}
    </div>
  );
}
