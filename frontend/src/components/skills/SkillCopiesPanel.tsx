// frontend/src/components/skills/SkillCopiesPanel.tsx
// What Check copies found (spec skill-manager "Report skill drift on
// request"): every agent's copy of every skill compared with the library, each
// finding listed with the skill, the agent, what differs, the path and the
// suggested remedy. Checking changes nothing on disk. Repair re-delivers what
// Coffer can put back on its own ("Repair repairable drift from master"); the
// findings it will not touch — a folder it did not make, a master that is
// gone — stay listed for the user.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, RefreshCw, Wrench, X } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { EmptyState } from "@/components/EmptyState";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillDriftEntry, SkillDriftReport, SkillRepairReport } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useRepairSkillCopies } from "@/lib/hooks/useSkills";

interface Props {
  report: SkillDriftReport | undefined;
  checking: boolean;
  onCheckAgain: () => void;
  onClose: () => void;
}

function Finding({ entry, repaired }: { entry: SkillDriftEntry; repaired: boolean }) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const agent = agents.find((a) => a.name === entry.agent_name);
  return (
    <li
      data-testid="skill-copy-finding"
      className="grid grid-cols-[minmax(0,10rem)_8rem_minmax(0,1fr)] items-start gap-4 px-4 py-3"
    >
      <span className="truncate font-mono text-xs font-label text-text">{entry.skill_name}</span>
      <span className="min-w-0">
        {agent ? (
          <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
        ) : (
          <span className="truncate text-xs text-text-muted">
            {entry.agent_name || t("skills.copies.library")}
          </span>
        )}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2">
          <StatusWord tone={repaired ? "ok" : "warn"}>
            {t(`skills.driftKind.${entry.kind}`)}
          </StatusWord>
          <span className="text-xs text-text-muted">
            {repaired ? t("skills.copies.repaired") : t("skills.copies.needsYou")}
          </span>
        </span>
        <span className="truncate font-mono text-xs text-text-muted">
          {abbreviateHomePath(entry.target_path)}
        </span>
        <span className="text-xs text-text-muted">{entry.suggested_remedy}</span>
      </span>
    </li>
  );
}

export function SkillCopiesPanel({ report, checking, onCheckAgain, onClose }: Props) {
  const { t } = useTranslation();
  const repair = useRepairSkillCopies();
  const [repairResult, setRepairResult] = useState<SkillRepairReport | null>(null);

  // After a repair, its own fresh report is the truth; a new check replaces it.
  const remaining = repairResult ? repairResult.remaining.entries : (report?.entries ?? []);
  const remediated = repairResult?.remediated ?? [];
  const total = remaining.length + remediated.length;

  const checkAgain = () => {
    setRepairResult(null);
    onCheckAgain();
  };

  return (
    <section aria-label={t("skills.copies.title")} className="flex flex-col gap-4">
      <header className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-lg font-bold">{t("skills.copies.title")}</h2>
          <p className="text-sm text-text-muted">{t("skills.copies.body")}</p>
        </div>
        <span className="inline-flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={checkAgain} disabled={checking}>
            <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
            {t("skills.copies.checkAgain")}
          </Button>
          {remaining.length > 0 && !checking ? (
            <Button
              size="sm"
              disabled={repair.isPending}
              onClick={() => repair.mutate(undefined, { onSuccess: setRepairResult })}
            >
              <Wrench aria-hidden />
              {repair.isPending ? t("skills.copies.repairing") : t("skills.copies.repair")}
            </Button>
          ) : null}
          <Button variant="ghost" size="icon-sm" aria-label={t("common.close")} onClick={onClose}>
            <X aria-hidden />
          </Button>
        </span>
      </header>

      {checking ? (
        <div className="space-y-2" aria-busy="true" aria-label={t("skills.copies.checking")}>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : total === 0 ? (
        report || repairResult ? (
          <EmptyState
            icon={CheckCircle2}
            title={t("skills.copies.allMatchTitle")}
            description={t("skills.copies.allMatchBody")}
          />
        ) : null
      ) : (
        <>
          <p className="text-xs text-text-muted">{t("skills.copies.summary", { count: total })}</p>
          <ul className="divide-y divide-border-subtle rounded-xl border border-border-subtle">
            {remaining.map((e) => (
              <Finding
                key={`r:${e.skill_name}:${e.agent_name}:${e.kind}`}
                entry={e}
                repaired={false}
              />
            ))}
            {remediated.map((e) => (
              <Finding key={`f:${e.skill_name}:${e.agent_name}:${e.kind}`} entry={e} repaired />
            ))}
          </ul>
          <p className="text-xs text-text-muted">{t("skills.copies.repairHint")}</p>
        </>
      )}
    </section>
  );
}
