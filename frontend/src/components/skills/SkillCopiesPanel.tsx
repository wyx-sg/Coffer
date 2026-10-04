// frontend/src/components/skills/SkillCopiesPanel.tsx
// "Check copies" (canvas 4.3.25; spec skill-manager "Report skill drift on
// request"): every agent's copy of every skill compared with the library. A
// 32 icon block, the title at 18/650 with one meta line, and Check again at the
// right; then two groups — Needs you and Fixed by Coffer — each finding one row:
// the skill, the agent (or Library), what differs and what it means, and the one
// button that answers it: Open skill (a missing master), Review… (a folder in the
// way — the compare dialog), Open (a folder that is not in the library) or Repair
// (a link that is missing or points elsewhere). Checking changes nothing on disk;
// Coffer repairs a missing link on its own and never overwrites a folder it
// didn't make, so those wait here for the reader.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, RefreshCw } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { EmptyState } from "@/components/EmptyState";
import { SkillCopyDialog } from "@/components/skills/SkillCopyDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillDriftEntry, SkillRepairReport } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useRepairSkillCopies, useSkillCopies, useSkills } from "@/lib/hooks/useSkills";
import { cn } from "@/lib/utils";

interface Props {
  /** Leaves the panel when a finding's button goes to a skill or a folder's own pane. */
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
  const action =
    entry.kind === "missing_link" || entry.kind === "tampered_link"
      ? t("skills.copies.repair")
      : entry.kind === "replaced_with_regular"
        ? t("skills.review")
        : entry.kind === "orphan_master"
          ? t("skills.copies.open")
          : t("skills.copies.openSkill");
  const dot = entry.kind === "missing_master" ? "bg-danger" : "bg-warning";
  return (
    <li
      data-testid="skill-copy-finding"
      className="grid grid-cols-[minmax(0,8rem)_8rem_minmax(0,1fr)_auto] items-start gap-3 py-2.5"
    >
      <span className="truncate font-mono text-sm font-medium text-text">{entry.skill_name}</span>
      <span className="min-w-0 pt-px">
        {agent ? (
          <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
        ) : (
          <span className="text-sm text-text-muted">{t("skills.copies.library")}</span>
        )}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex items-center gap-1.5 text-sm font-medium text-text">
          {repaired ? null : (
            <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", dot)} />
          )}
          {repaired ? t("skills.copies.fixedTitle") : t(`skills.driftKind.${entry.kind}`)}
        </span>
        <span className="text-xs text-text-muted">
          {repaired
            ? t(`skills.copies.fixed.${entry.kind}`)
            : t(`skills.copies.about.${entry.kind}`, {
                path: abbreviateHomePath(entry.target_path),
              })}
        </span>
      </span>
      <span className="justify-self-end">
        {repaired ? null : (
          <Button variant="outline" size="sm" disabled={busy} onClick={() => onAction(entry)}>
            {action}
          </Button>
        )}
      </span>
    </li>
  );
}

function Group({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title} className="flex flex-col">
      <h3 className="flex items-center pb-1.5 pt-3.5 text-2xs font-semibold text-text-subtle">
        {title}
        <span className="ml-auto font-normal">{count}</span>
      </h3>
      <ul className="divide-y divide-border-subtle">{children}</ul>
    </section>
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
    <section aria-label={t("skills.copies.title")} className="flex flex-col gap-2.5">
      <header className="flex items-center gap-3">
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <RefreshCw className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-lg font-bold">{t("skills.copies.title")}</h2>
          <p className="text-xs text-text-muted">
            {t("skills.copies.meta")}
            {checking
              ? ` · ${t("skills.copies.checking")}`
              : copies.data || repairResult
                ? ` · ${t("skills.copies.checkedNow")}`
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
          {remaining.length > 0 ? (
            <Group title={t("skills.copies.needsYou")} count={remaining.length}>
              {remaining.map((e) => (
                <Finding
                  key={`r:${e.skill_name}:${e.agent_name}:${e.kind}`}
                  entry={e}
                  repaired={false}
                  onAction={act}
                  busy={repair.isPending}
                />
              ))}
            </Group>
          ) : null}
          {remediated.length > 0 ? (
            <Group title={t("skills.copies.fixedGroup")} count={remediated.length}>
              {remediated.map((e) => (
                <Finding
                  key={`f:${e.skill_name}:${e.agent_name}:${e.kind}`}
                  entry={e}
                  repaired
                  onAction={act}
                  busy={false}
                />
              ))}
            </Group>
          ) : null}
          <p className="pt-2 text-xs text-text-muted">{t("skills.copies.repairHint")}</p>
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
