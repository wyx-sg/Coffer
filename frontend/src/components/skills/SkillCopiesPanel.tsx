// frontend/src/components/skills/SkillCopiesPanel.tsx
// "Check agents' copies" (canvas 4.3.21; spec skill-manager "Report skill
// drift on request"): every agent's copy of every skill compared with the
// library, one row per finding — the skill, the agent (or Library), what
// differs and what it means, whether it needs the reader, and the one action
// that answers it: Review… a folder in the way (the compare dialog), a missing
// master (its page) or a folder that is not in the library (its pane); Repair
// a missing or repointed link. Checking changes nothing on disk; Coffer
// repairs a missing link on its own and never overwrites a folder it didn't
// make, so those wait here for the reader.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, RefreshCw, X } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { EmptyState } from "@/components/EmptyState";
import { SkillCopyDialog } from "@/components/skills/SkillCopyDialog";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillDriftEntry, SkillRepairReport } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useRepairSkillCopies, useSkillCopies, useSkills } from "@/lib/hooks/useSkills";

interface Props {
  onClose: () => void;
}

function Finding({
  entry,
  repaired,
  onAction,
  busy,
}: {
  entry: SkillDriftEntry;
  repaired: boolean;
  onAction: (entry: SkillDriftEntry) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const agent = agents.find((a) => a.name === entry.agent_name);
  const repairable = entry.kind === "missing_link" || entry.kind === "tampered_link";
  const status = repaired
    ? t("skills.copies.repaired")
    : entry.kind === "replaced_with_regular"
      ? t("skills.copies.leftAlone")
      : t("skills.copies.needsYou");
  return (
    <li
      data-testid="skill-copy-finding"
      className="grid grid-cols-[minmax(0,8rem)_8rem_minmax(0,1fr)_8.5rem_6rem] items-center gap-4 py-3"
    >
      <span className="truncate font-mono text-xs font-label text-text">{entry.skill_name}</span>
      <span className="min-w-0">
        {agent ? (
          <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
        ) : (
          <span className="text-xs text-text-muted">{t("skills.copies.library")}</span>
        )}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm text-text">{t(`skills.driftKind.${entry.kind}`)}</span>
        <span className="text-xs text-text-muted">
          {t(`skills.copies.about.${entry.kind}`, { path: abbreviateHomePath(entry.target_path) })}
        </span>
      </span>
      <StatusWord tone={repaired ? "ok" : "warn"}>{status}</StatusWord>
      <span className="justify-self-end">
        {repaired ? null : (
          <Button variant="outline" size="sm" disabled={busy} onClick={() => onAction(entry)}>
            {repairable ? t("skills.copies.repair") : t("skills.review")}
          </Button>
        )}
      </span>
    </li>
  );
}

export function SkillCopiesPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const copies = useSkillCopies();
  const { data: skills = [] } = useSkills();
  const repair = useRepairSkillCopies();
  const [repairResult, setRepairResult] = useState<SkillRepairReport | null>(null);
  const [reviewing, setReviewing] = useState<SkillDriftEntry | null>(null);
  const checking = copies.isFetching;

  // After a repair, its own fresh report is the truth; a new check replaces it.
  const remaining = repairResult ? repairResult.remaining.entries : (copies.data?.entries ?? []);
  const remediated = repairResult?.remediated ?? [];
  const total = remaining.length + remediated.length;
  const reviewSkill = reviewing ? skills.find((s) => s.name === reviewing.skill_name) : undefined;

  const act = (entry: SkillDriftEntry) => {
    if (entry.kind === "missing_link" || entry.kind === "tampered_link") {
      repair.mutate(undefined, { onSuccess: setRepairResult });
    } else if (entry.kind === "replaced_with_regular") {
      setReviewing(entry);
    } else if (entry.kind === "orphan_master") {
      onClose();
      navigate(`/skills?orphan=${encodeURIComponent(entry.skill_name)}`);
    } else {
      onClose();
      navigate(`/skills/${encodeURIComponent(entry.skill_name)}`);
    }
  };

  return (
    <section aria-label={t("skills.copies.title")} className="flex flex-col gap-4">
      <header className="flex items-start gap-3 border-b border-border-subtle pb-4">
        <span className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <RefreshCw className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-lg font-bold">{t("skills.copies.title")}</h2>
          <p className="text-sm text-text-muted">
            {t("skills.copies.body")}{" "}
            {checking
              ? t("skills.copies.checking")
              : copies.data || repairResult
                ? t("skills.copies.summary", { count: total, fixed: remediated.length })
                : null}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setRepairResult(null);
            void copies.refetch();
          }}
          disabled={checking}
        >
          <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
          {t("skills.copies.checkAgain")}
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label={t("common.close")} onClick={onClose}>
          <X aria-hidden />
        </Button>
      </header>

      {checking ? (
        <div className="space-y-2" aria-busy="true" aria-label={t("skills.copies.checking")}>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : total === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title={t("skills.copies.allMatchTitle")}
          description={t("skills.copies.allMatchBody")}
        />
      ) : (
        <>
          <ul className="-mt-4 divide-y divide-border-subtle">
            {remaining.map((e) => (
              <Finding
                key={`r:${e.skill_name}:${e.agent_name}:${e.kind}`}
                entry={e}
                repaired={false}
                onAction={act}
                busy={repair.isPending}
              />
            ))}
            {remediated.map((e) => (
              <Finding
                key={`f:${e.skill_name}:${e.agent_name}:${e.kind}`}
                entry={e}
                repaired
                onAction={act}
                busy={false}
              />
            ))}
          </ul>
          <p className="text-xs text-text-muted">{t("skills.copies.repairHint")}</p>
        </>
      )}

      {reviewSkill ? (
        <SkillCopyDialog
          skill={reviewSkill}
          entry={reviewing}
          onOpenChange={(open) => !open && setReviewing(null)}
        />
      ) : null}
    </section>
  );
}
