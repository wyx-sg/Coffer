// frontend/src/components/skills/SkillLibraryRow.tsx
// One row of the Skills library (canvas 4.3 SkillsList): a state dot, the
// skill's name (with "Built-in" beside Coffer's own), a second line only when
// something needs the reader (lib/skills/attention.ts: its master is gone, a
// folder is in the way of an agent's link, a command or tool it needs is not
// ready, its Git source is unreachable or has an update) — the description is
// on the skill's page, not here — and its reach on the right: All agents, or the badges
// of the agents it is restricted to. An Off skill shows no reach word (the
// group says it, as in the MCP servers list). The checkbox feeds the selection
// bar; it shows on hover, and on every row while any is ticked. The built-in
// row has none: it is never part of a bulk action.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { StatusDot } from "@/components/status/StatusDot";
import { Checkbox } from "@/components/ui/checkbox";
import type { AgentOut } from "@/lib/api/agents";
import type { Cli } from "@/lib/api/clis";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { skillAttention, isProblem, type SkillAttention } from "@/lib/skills/attention";
import { toneTextClass } from "@/lib/statusColors";
import type { StatusTone } from "@/lib/statusTone";
import { openRowTarget } from "@/lib/rowClick";
import { cn } from "@/lib/utils";

interface Props {
  skill: SkillOut;
  agents: readonly AgentOut[];
  clis: readonly Cli[];
  drift: SkillDriftEntry[] | undefined;
  /** Any row is ticked: every checkbox shows. */
  selecting: boolean;
  to: string;
  current: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onOpen: () => void;
}

function useSublineText(item: SkillAttention, agents: readonly AgentOut[]): string {
  const { t } = useTranslation();
  switch (item.kind) {
    case "masterMissing":
      return t("skills.row.masterMissing");
    case "folderInWay": {
      const agent = agents.find((a) => a.name === item.agentName);
      return t("skills.row.folderInWay", { agent: agent?.display_name ?? item.agentName });
    }
    case "requires":
      if (item.missing.length > 0) {
        return t("skills.row.needsMissing", { command: item.missing[0] });
      }
      if (item.loggedOut.length > 0) {
        return t("skills.row.needsLogin", { command: item.loggedOut[0] });
      }
      return t("skills.row.needsNewer", { command: item.outdated[0] });
    case "toolOff": {
      const tool = item.tools[0];
      return t("skills.row.needsTool", {
        name: tool?.name,
        state: t(`skills.requires.toolState.${tool?.status ?? "off"}`).toLowerCase(),
      });
    }
    case "secrets":
      return t("skills.row.needsSecret", { name: item.missing[0] });
    case "sourceUnreachable":
      return t("skills.row.sourceUnreachable");
    case "updateAvailable":
      return t("skills.row.updateAvailable");
  }
}

function subTone(item: SkillAttention): string {
  if (item.kind === "masterMissing") return toneTextClass("error");
  if (!isProblem(item)) return "text-text-muted";
  return toneTextClass("warn");
}

function Subline({ item, agents }: { item: SkillAttention; agents: readonly AgentOut[] }) {
  const text = useSublineText(item, agents);
  return <span className={cn("truncate text-xs", subTone(item))}>{text}</span>;
}

/** The dot before the name: red for a missing master, amber for any other
 *  problem, green for a skill in use, grey for one that is off. */
function dotTone(skill: SkillOut, attention: SkillAttention | undefined): StatusTone {
  if (attention?.kind === "masterMissing") return "err";
  if (attention && isProblem(attention)) return "warn";
  return skill.enabled ? "ok" : "off";
}

function ReachMark({ skill, agents }: { skill: SkillOut; agents: readonly AgentOut[] }) {
  const { t } = useTranslation();
  if (!skill.enabled) return null;
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
  clis,
  drift,
  selecting,
  to,
  current,
  checked,
  onCheckedChange,
  onOpen,
}: Props) {
  const { t } = useTranslation();
  // Built-in skills are never a problem to fix.
  const attention = (skill.builtin ? [] : skillAttention(skill, clis, drift))[0];
  return (
    <li
      onClick={openRowTarget}
      className={cn(
        "group flex cursor-pointer items-center gap-2 rounded-lg pl-2.5 transition-colors duration-fast",
        current ? "bg-surface-selected" : "hover:bg-surface-hover",
      )}
    >
      {skill.builtin ? null : (
        <span
          className={cn(
            "shrink-0 items-center",
            selecting || checked
              ? "inline-flex"
              : "hidden group-focus-within:inline-flex group-hover:inline-flex",
          )}
        >
          <Checkbox
            checked={checked}
            onChange={(e) => onCheckedChange(e.target.checked)}
            aria-label={`${t("common.bulk.selectRow")}: ${skill.name}`}
          />
        </span>
      )}
      <Link
        to={to}
        data-row-open
        onClick={onOpen}
        aria-current={current ? "page" : undefined}
        className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg py-2 pr-2.5 text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
      >
        <StatusDot tone={dotTone(skill, attention)} size={7} className="self-center" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-mono text-xs font-label">{skill.name}</span>
            {skill.builtin ? (
              <span
                data-testid="skill-builtin-badge"
                className="text-2xs font-label text-text-muted"
              >
                {t("skills.builtinBadge")}
              </span>
            ) : null}
          </span>
          {attention ? <Subline item={attention} agents={agents} /> : null}
        </span>
        <span className="shrink-0">
          <ReachMark skill={skill} agents={agents} />
        </span>
      </Link>
    </li>
  );
}
