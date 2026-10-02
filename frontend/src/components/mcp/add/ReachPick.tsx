// frontend/src/components/mcp/add/ReachPick.tsx — the "Available to" choice for
// servers not registered yet: the shared ReachControl, driven by local intent
// instead of a stored scope. The dialog writes the intent after registering
// (importMcpServers.ts `applyReach`); the default is every agent.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import type { ReachIntent } from "@/lib/mcp/importMcpServers";

interface Props {
  value: ReachIntent;
  onChange: (next: ReachIntent) => void;
  busy?: boolean;
}

export function ReachPick({ value, onChange, busy = false }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-text-muted">{t("scope.availableTo")}</span>
      <ReachControl
        mode={value.mode}
        busy={busy}
        initialScope={value.mode === "restricted" ? { agents: value.agents } : null}
        onDisabled={() => onChange({ mode: "disabled" })}
        onEverywhere={() => onChange({ mode: "everywhere" })}
        onRestricted={(scope) => onChange({ mode: "restricted", agents: scope.agents ?? [] })}
        testId="add-server-reach"
      />
    </div>
  );
}
