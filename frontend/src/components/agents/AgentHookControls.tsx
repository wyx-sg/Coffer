// frontend/src/components/agents/AgentHookControls.tsx — slice 6 (rules injection).
// Session-start hook control, rendered as a toggle ROW (title + help on the
// left, a Switch on the right) so it sits inside the Memory tab's combined box
// next to the "disable native memory" toggle — both govern what Coffer feeds the
// agent at session start. Toggling the switch on installs the SessionStart hook
// (POST), off uninstalls it (DELETE), with pending state + inline error. When
// the agent type has no hook support the status read fails with a 422
// HOOK_INSTALL_UNSUPPORTED — we present a disabled switch + explanatory text so a
// hook-less agent type never shows a broken control. No Card wrapper: the parent
// provides the box + padding.
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useAgentHookInstall, useAgentHookStatus } from "@/lib/hooks/useAgents";

/**
 * Session-start hook toggle row. Reads install status; when the agent type
 * doesn't support hooks (422 `HOOK_INSTALL_UNSUPPORTED`), renders a disabled
 * switch with an explanatory line instead of a control that would always fail.
 */
export function AgentHookToggle({ name }: { name: string }) {
  const { t } = useTranslation();
  const status = useAgentHookStatus(name);
  const mutate = useAgentHookInstall(name);

  const unsupported =
    status.error instanceof ApiError && status.error.code === "HOOK_INSTALL_UNSUPPORTED";
  const installed = status.data?.installed ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <Label htmlFor="agent-hook-toggle" className="text-sm font-medium">
            {t("agents.hook.title")}
          </Label>
          <p className="max-w-prose text-xs text-muted-foreground">
            {unsupported ? t("agents.hook.unsupported") : t("agents.hook.help")}
          </p>
        </div>
        <Switch
          id="agent-hook-toggle"
          checked={installed}
          disabled={unsupported || mutate.isPending || status.isPending}
          onCheckedChange={(v) => mutate.mutate(v)}
          aria-label={t("agents.hook.install")}
        />
      </div>
      {mutate.error ? (
        <p className="text-xs text-destructive">{translateApiError(t, mutate.error)}</p>
      ) : null}
    </div>
  );
}
