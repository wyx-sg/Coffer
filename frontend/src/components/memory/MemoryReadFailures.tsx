// frontend/src/components/memory/MemoryReadFailures.tsx
//
// The banner the Memory overview shows when the last read left an agent's
// memory unread (design 5.2.03, spec memory "Report the last read of the
// agents' memory"): which agent, which path and why, that its memories stay as
// its last full read left them, with Retry (Update memory) and [Ask an agent]
// carrying a prompt to fix the read permission.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AskAgentButton } from "@/components/handoff/AskAgentButton";
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
            className="flex items-start gap-2.5 rounded-lg bg-warning-soft px-3 py-2.5"
          >
            <AlertTriangle className="mt-px size-[15px] shrink-0 text-warning" aria-hidden />
            <div className="flex min-w-0 grow flex-col gap-[3px]">
              <span className="text-sm font-label text-text">
                {t("memory.failure.title", { agent })}{" "}
                <span className="font-mono text-xs">{abbreviateHomePath(f.path)}</span>
                {f.reason ? <span className="text-xs font-normal"> {f.reason}</span> : null}
              </span>
              <span className="text-xs text-text-muted">
                {f.last_read_at
                  ? t("memory.failure.keptSince", {
                      agent,
                      date: shortDate(f.last_read_at, i18n.language),
                    })
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
              <AskAgentButton
                prompt={t("memory.failure.prompt", {
                  agent,
                  path: f.path,
                  reason: f.reason || t("memory.failure.noReason"),
                })}
              />
            </span>
          </div>
        );
      })}
    </div>
  );
}
