// src/components/agents/AgentSkillsTab.tsx — the agent's Skills tab: Coffer's part first, then the agent's own skills.
//
// Boards 2.1.20–2.1.24. "From Coffer" is one row — how many skills Coffer
// delivers into this agent and their first names — linking to the Skills page
// filtered to this agent; Coffer's skills are not listed one by one. Below it
// the agent's own skills: folders Coffer does not manage, the only place in the
// UI that lists or adopts them (spec skill-manager "Expose unmanaged-skill operations on REST and the web"). Adopt opens a dialog (name, reach); a
// duplicate of a skill Coffer delivers is deleted from here.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkle } from "lucide-react";

import { Section } from "@/components/Section";
import { AdoptSkillDialog } from "@/components/agents/skills/AdoptSkillDialog";
import { AgentOwnSkillRows } from "@/components/agents/skills/AgentOwnSkillRows";
import { DeleteOwnSkillDialog } from "@/components/agents/skills/DeleteOwnSkillDialog";
import {
  buildOwnSkillRows,
  cofferSkillNames,
  type OwnSkillRow,
} from "@/components/agents/skills/skillRows";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { FromCofferRow } from "@/components/agents/tabs/FromCofferRow";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useDeleteUnmanagedSkill, useUnmanagedSkills } from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";

export function AgentSkillsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const skills = useSkills();
  const unmanaged = useUnmanagedSkills(agent.uid);
  const remove = useDeleteUnmanagedSkill(agent.uid);
  const [adoptTarget, setAdoptTarget] = useState<OwnSkillRow | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<OwnSkillRow | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<OwnSkillRow | null>(null);
  const agentLabel = agentTypeLabel(agent.type);

  const cofferNames = useMemo(
    () => cofferSkillNames(agent.uid, skills.data ?? []),
    [agent.uid, skills.data],
  );
  const rows = useMemo(
    () => buildOwnSkillRows(unmanaged.data?.items ?? [], cofferNames),
    [unmanaged.data, cofferNames],
  );

  return (
    <div className="flex max-w-[1000px] flex-col gap-8">
      {skills.data ? (
        <FromCofferRow
          icon={Sparkle}
          testId="from-coffer-skills"
          description={t("agents.skillsTab.fromCoffer.description", { agent: agentLabel })}
          title={t("agents.skillsTab.fromCoffer.title", { count: cofferNames.length })}
          names={cofferNames}
          linkLabel={t("agents.skillsTab.fromCoffer.open")}
          to={`/skills?agent=${encodeURIComponent(agent.uid)}`}
        />
      ) : null}

      <Section
        as="h2"
        title={t("agents.skillsTab.own.title", { agent: agentLabel })}
        help={t("agents.skillsTab.own.help")}
        gap="tight"
        testId="own-skills-section"
      >
        <p className="mb-1 text-xs text-text-muted">
          {t("agents.skillsTab.own.description", { agent: agentLabel })}
        </p>
        <AgentKindTab
          rows={rows}
          searchPlaceholder={t("agents.skillsTab.search")}
          searchText={(row) => row.name}
          isLoading={unmanaged.isPending}
          error={unmanaged.error}
          onRetry={() => void unmanaged.refetch()}
          empty={{
            title: t("agents.skillsTab.emptyTitle", { agent: agentLabel }),
            description: t("agents.skillsTab.emptyDescription", { agent: agentLabel }),
          }}
          noMatch={t("agents.skillsTab.noMatch")}
        >
          {(visible) => (
            <AgentOwnSkillRows
              agentType={agent.type}
              rows={visible}
              onAdopt={setAdoptTarget}
              onDeleteDuplicate={setDuplicateTarget}
              onDelete={setDeleteTarget}
            />
          )}
        </AgentKindTab>
      </Section>

      <AdoptSkillDialog
        agentUid={agent.uid}
        row={adoptTarget}
        onOpenChange={(next) => {
          if (!next) setAdoptTarget(null);
        }}
      />

      <DeleteOwnSkillDialog
        agentUid={agent.uid}
        target={deleteTarget}
        pending={remove.isPending}
        onOpenChange={(next) => {
          if (!next) setDeleteTarget(null);
        }}
        onConfirm={(row) =>
          remove.mutate(
            { skill: row.name, location: row.item.location },
            { onSuccess: () => setDeleteTarget(null) },
          )
        }
      />

      <ConfirmDialog
        open={duplicateTarget !== null}
        onOpenChange={(next) => {
          if (!next) setDuplicateTarget(null);
        }}
        title={t("agents.skillsTab.removeDuplicateTitle", { name: duplicateTarget?.name ?? "" })}
        description={t("agents.skillsTab.removeDuplicateBody", {
          name: duplicateTarget?.name ?? "",
          path: duplicateTarget ? abbreviateHomePath(duplicateTarget.item.path) : "",
          agent: agentLabel,
        })}
        confirmLabel={t("common.delete")}
        pending={remove.isPending}
        onConfirm={() => {
          if (!duplicateTarget) return;
          remove.mutate(
            { skill: duplicateTarget.name, location: duplicateTarget.item.location },
            { onSuccess: () => setDuplicateTarget(null) },
          );
        }}
      />
    </div>
  );
}
