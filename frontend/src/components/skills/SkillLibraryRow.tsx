// frontend/src/components/skills/SkillLibraryRow.tsx
// One row of the Skills library: the skill's name with its marks (Built-in,
// Copied), a second line that is its description unless something needs
// saying (its Git source is unreachable, or an update is waiting), and its
// reach on the right — Off, All agents, or the badges of the agents it is
// restricted to. The checkbox beside it feeds the bulk bar; the built-in row
// has none, since the bar's one destructive action would have to refuse it.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { BuiltinMark, CopiedMark } from "@/components/skills/SkillMarks";
import { StatusWord } from "@/components/status/StatusWord";
import { Checkbox } from "@/components/ui/checkbox";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillOut } from "@/lib/api/skills";
import { hasCopiedDelivery } from "@/lib/skills/delivery";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

interface Props {
  skill: SkillOut;
  agents: readonly AgentOut[];
  to: string;
  current: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onOpen: () => void;
}

function SkillSubline({ skill }: { skill: SkillOut }) {
  const { t } = useTranslation();
  const status = skill.source_status;
  if (status?.error) {
    return (
      <span className={cn("truncate text-xs", toneTextClass("warn"))}>
        {t("skills.sourceUnreachable")}
      </span>
    );
  }
  if (status?.update_available) {
    return (
      <span className={cn("truncate text-xs", toneTextClass("warn"))}>
        {t("skills.updateAvailable")}
      </span>
    );
  }
  return <span className="truncate text-xs text-text-muted">{skill.description}</span>;
}

function ReachMark({ skill, agents }: { skill: SkillOut; agents: readonly AgentOut[] }) {
  const { t } = useTranslation();
  if (!skill.enabled) return <StatusWord tone="off">{t("skills.offMark")}</StatusWord>;
  const scoped = skill.scope?.agents ?? null;
  if (scoped === null) {
    return <span className="text-xs text-text-muted">{t("agentBadge.allAgents")}</span>;
  }
  const chosen = agents.filter((a) => scoped.includes(a.uid));
  if (chosen.length === 0) {
    return <span className="text-xs text-text-muted">{t("scope.noneSelected")}</span>;
  }
  return (
    <AgentBadgeGroup
      agents={chosen.map((a) => ({ type: a.type, name: a.display_name }))}
      total={agents.length}
      className="text-xs text-text-muted"
    />
  );
}

export function SkillLibraryRow({
  skill,
  agents,
  to,
  current,
  checked,
  onCheckedChange,
  onOpen,
}: Props) {
  const { t } = useTranslation();
  return (
    <li
      className={cn(
        "group flex items-center gap-2 rounded-lg pl-2.5 transition-colors duration-fast",
        current ? "bg-surface-selected" : "hover:bg-surface-hover",
      )}
    >
      {skill.builtin ? (
        // Keeps the names aligned with the rows that have a checkbox.
        <span aria-hidden className="size-[15px] shrink-0" />
      ) : (
        <Checkbox
          checked={checked}
          onChange={(e) => onCheckedChange(e.target.checked)}
          aria-label={`${t("common.bulk.selectRow")}: ${skill.name}`}
        />
      )}
      <Link
        to={to}
        onClick={onOpen}
        aria-current={current ? "page" : undefined}
        className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg py-2 pr-2.5 text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-mono text-xs font-label">{skill.name}</span>
            {skill.builtin ? <BuiltinMark /> : null}
            {hasCopiedDelivery(skill) ? <CopiedMark /> : null}
          </span>
          <SkillSubline skill={skill} />
        </span>
        <span className="shrink-0">
          <ReachMark skill={skill} agents={agents} />
        </span>
      </Link>
    </li>
  );
}
