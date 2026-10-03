// frontend/src/components/mcp/add/ReachPick.tsx — the "Available to" choice for
// servers not registered yet (boards Mcp-Add-TestPassed, Mcp-Import-Review): the
// label above, the shared ReachControl driven by local intent instead of a stored
// scope, and one help line. The dialog writes the intent after registering
// (importMcpServers.ts `applyReach`); the default is every agent.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import type { ReachIntent } from "@/lib/mcp/importMcpServers";

interface Props {
  value: ReachIntent;
  onChange: (next: ReachIntent) => void;
  busy?: boolean;
  /** One server (the form) or every server of a review. */
  scope?: "one" | "batch";
}

export function ReachPick({ value, onChange, busy = false, scope = "one" }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-start gap-1.5">
      <span className="text-xs font-label text-text">{t("scope.availableTo")}</span>
      <ReachControl
        mode={value.mode}
        busy={busy}
        initialScope={value.mode === "restricted" ? { agents: value.agents } : null}
        onDisabled={() => onChange({ mode: "disabled" })}
        onEverywhere={() => onChange({ mode: "everywhere" })}
        onRestricted={(picked) => onChange({ mode: "restricted", agents: picked.agents ?? [] })}
        testId="add-server-reach"
      />
      <span className="text-xs leading-snug text-text-muted">
        {scope === "batch" ? t("mcp.add.reachHelpBatch") : t("mcp.add.reachHelp")}
      </span>
    </div>
  );
}
