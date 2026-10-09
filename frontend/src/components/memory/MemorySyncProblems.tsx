// frontend/src/components/memory/MemorySyncProblems.tsx
//
// What the last sync could not do, above the page's blocks (spec memory "Fail a
// broken reader loudly and in isolation", "Withhold a memory that looks like a
// secret"): each source it could not read — that agent contributed nothing from
// it, and what it published earlier stays — with its path and reason, and each
// memory it withheld because it looked like a secret, by agent and path only.
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { SourceProblem } from "@/lib/memory/syncFacts";

interface Props {
  failures: readonly SourceProblem[];
  withheld: readonly SourceProblem[];
}

function Lines({ items, reason }: { items: readonly SourceProblem[]; reason: boolean }) {
  return (
    <ul className="space-y-0.5">
      {items.map((p) => (
        <li key={`${p.agent}:${p.path}`} className="[overflow-wrap:anywhere]">
          {agentTypeLabel(p.agent)} ·{" "}
          <span className="font-mono text-xs">{abbreviateHomePath(p.path)}</span>
          {reason && p.reason ? ` — ${p.reason}` : null}
        </li>
      ))}
    </ul>
  );
}

export function MemorySyncProblems({ failures, withheld }: Props) {
  const { t } = useTranslation();
  if (failures.length === 0 && withheld.length === 0) return null;
  return (
    <div className="flex flex-col gap-2" data-testid="memory-sync-problems">
      {failures.length > 0 ? (
        <Alert variant="warning">
          <AlertTitle>{t("memory.problems.failed", { count: failures.length })}</AlertTitle>
          <AlertDescription>
            <Lines items={failures} reason />
            <p className="mt-1 text-xs text-text-muted">{t("memory.problems.failedKept")}</p>
          </AlertDescription>
        </Alert>
      ) : null}
      {withheld.length > 0 ? (
        <Alert variant="warning">
          <AlertTitle>{t("memory.problems.withheld", { count: withheld.length })}</AlertTitle>
          <AlertDescription>
            <Lines items={withheld} reason={false} />
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
