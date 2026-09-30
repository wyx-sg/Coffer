// frontend/src/components/memory/MemoryReadFailures.tsx
//
// The banner the Memory overview shows when the last read left an agent's
// memory unread (design 5.2.02, spec memory "Report the last read of the
// agents' memory"): which agent, which path and why, that its memories stay as
// its last full read left them, with Retry (Update memory) and Open Activity.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { useMemoryReading, useSyncMemory } from "@/lib/hooks/useMemory";
import { agentTypeOfOrigin } from "./memoryAgents";

/** "Sep 27" in the UI language. */
function shortDate(iso: string, language: string): string {
  return new Date(iso).toLocaleDateString(language, { month: "short", day: "numeric" });
}

export function MemoryReadFailures() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const reading = useMemoryReading();
  const retry = useSyncMemory();
  const failures = reading.data?.failures ?? [];
  if (failures.length === 0) return null;

  return (
    <div className="flex flex-col gap-2" data-testid="memory-read-failures">
      {failures.map((f) => {
        const agent = f.agent
          ? agentTypeLabel(agentTypeOfOrigin(f.agent))
          : t("memory.failure.anAgent");
        return (
          <div
            key={`${f.agent}:${f.path}`}
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-status-warn/30 bg-status-warn/10 px-3.5 py-3"
          >
            <AlertTriangle className="mt-px size-4 shrink-0 text-status-warn" aria-hidden />
            <div className="flex min-w-0 grow flex-col gap-0.5">
              <span className="text-sm font-medium text-text">
                {t("memory.failure.title", { agent })}{" "}
                <span className="font-mono text-xs">{abbreviateHomePath(f.path)}</span>
                {f.reason ? ` — ${f.reason}` : null}
              </span>
              <span className="text-xs text-text-muted">
                {f.last_read_at
                  ? t("memory.failure.keptSince", { agent, date: shortDate(f.last_read_at, i18n.language) })
                  : t("memory.failure.kept", { agent })}
              </span>
            </div>
            <span className="flex shrink-0 gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={retry.isPending}
                onClick={() => retry.mutate()}
              >
                {t("memory.failure.retry")}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => navigate("/activity")}>
                {t("memory.failure.openActivity")}
              </Button>
            </span>
          </div>
        );
      })}
    </div>
  );
}
