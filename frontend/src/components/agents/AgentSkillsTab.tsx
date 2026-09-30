// src/components/agents/AgentSkillsTab.tsx — the agent's Skills tab: Coffer's delivered skills and the agent's own, in one table.
//
// Board 2.1.20, spec agent-registry "Filter an agent's installed kinds by
// owner". Coffer's rows are the managed skills linked into this agent; which
// agents get a skill is decided on the Skills page, which the footnote points
// at. The agent's own rows are the skill folders Coffer does not manage — the
// only place in the UI that lists or adopts them (spec skill-manager "Expose
// unmanaged-skill operations on REST, CLI and web"). A failed adoption stays on
// its row and in a line under the table (board 2.1.22), besides the hook's toast.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { AgentSkillsTable } from "@/components/agents/skills/AgentSkillsTable";
import { DeleteOwnSkillDialog } from "@/components/agents/skills/DeleteOwnSkillDialog";
import {
  buildSkillRows,
  ownSkillKey,
  type AdoptFailure,
  type OwnSkillRow,
} from "@/components/agents/skills/skillRows";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { countByOwner } from "@/lib/agents/owner";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useFsActions } from "@/lib/fsActions";
import {
  useAdoptUnmanagedSkill,
  useDeleteUnmanagedSkill,
  useUnmanagedSkills,
} from "@/lib/hooks/useAgents";
import { useSkills } from "@/lib/hooks/useSkills";

export function AgentSkillsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { open } = useFsActions();
  const skills = useSkills();
  const unmanaged = useUnmanagedSkills(agent.uid);
  const adopt = useAdoptUnmanagedSkill(agent.uid);
  const remove = useDeleteUnmanagedSkill(agent.uid);
  const [failure, setFailure] = useState<AdoptFailure | null>(null);
  const [adoptingKey, setAdoptingKey] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<OwnSkillRow | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<OwnSkillRow | null>(null);
  const agentLabel = agentTypeLabel(agent.type);

  const rows = useMemo(
    () =>
      buildSkillRows(agent.uid, skills.data ?? [], unmanaged.data?.items ?? [], failure, {
        foreign: t("agents.skillsTab.foreignDescription"),
        duplicateOf: (name) => t("agents.skillsTab.duplicateOf", { name }),
      }),
    [agent.uid, skills.data, unmanaged.data, failure, t],
  );
  const counts = countByOwner(rows);

  const onAdopt = (row: OwnSkillRow) => {
    const key = ownSkillKey(row.item);
    setAdoptingKey(key);
    setFailure(null);
    adopt.mutate(
      { skill: row.name, location: row.item.location },
      {
        onSuccess: (ref) => toast.success(t("agents.skillsTab.adoptSuccess", { name: ref.name })),
        onError: (err) => setFailure({ key, name: row.name, reason: translateApiError(t, err) }),
        onSettled: () => setAdoptingKey(null),
      },
    );
  };

  const onOpenFile = (path: string) =>
    void open(path, "").catch(() => toast.error(t("agents.skillsTab.openFileFailed")));

  // "Open it" when the name the adoption collided with is a managed skill.
  const clash = failure ? (skills.data ?? []).find((s) => s.name === failure.name) : undefined;

  return (
    <>
      <AgentKindTab
        rows={rows}
        summary={t("agents.skillsTab.summary", {
          count: rows.length,
          coffer: counts.coffer,
          own: counts.own,
        })}
        searchPlaceholder={t("agents.skillsTab.search")}
        searchText={(row) => `${row.name} ${row.description ?? ""} ${row.path ?? ""}`}
        isLoading={skills.isPending || unmanaged.isPending}
        error={unmanaged.error ?? skills.error}
        onRetry={() => {
          void skills.refetch();
          void unmanaged.refetch();
        }}
        empty={{
          icon: Sparkles,
          title: t("agents.skillsTab.emptyTitle", { agent: agentLabel }),
          description: t("agents.skillsTab.emptyDescription", { agent: agentLabel }),
        }}
        footnote={
          <>
            {t("agents.skillsTab.footnoteBefore")}{" "}
            <Link to="/skills" className="text-text underline-offset-2 hover:underline">
              {t("agents.skillsTab.footnoteLink")}
            </Link>{" "}
            {t("agents.skillsTab.footnoteAfter")}
          </>
        }
      >
        {(visible) => (
          <AgentSkillsTable
            agentType={agent.type}
            rows={visible}
            adoptingKey={adoptingKey}
            onAdopt={onAdopt}
            onRemoveDuplicate={setRemoveTarget}
            onOpenFile={onOpenFile}
            onDelete={setDeleteTarget}
          />
        )}
      </AgentKindTab>

      {failure ? (
        <Alert variant="error" className="mt-3.5">
          <AlertDescription className="flex flex-wrap items-center gap-2">
            {t("agents.skillsTab.adoptFailedBanner", {
              name: failure.name,
              reason: failure.reason,
            })}
            {clash ? (
              <Link
                to={`/skills/${encodeURIComponent(clash.name)}`}
                className="font-label text-text underline-offset-2 hover:underline"
              >
                {t("agents.skillsTab.adoptFailedOpen")}
              </Link>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

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
        open={removeTarget !== null}
        onOpenChange={(next) => {
          if (!next) setRemoveTarget(null);
        }}
        title={t("agents.skillsTab.removeDuplicateTitle", { name: removeTarget?.name ?? "" })}
        description={t("agents.skillsTab.removeDuplicateBody", {
          name: removeTarget?.name ?? "",
          path: removeTarget ? abbreviateHomePath(removeTarget.item.path) : "",
          agent: agentLabel,
        })}
        confirmLabel={t("common.delete")}
        pending={remove.isPending}
        onConfirm={() => {
          if (!removeTarget) return;
          remove.mutate(
            { skill: removeTarget.name, location: removeTarget.item.location },
            { onSuccess: () => setRemoveTarget(null) },
          );
        }}
      />
    </>
  );
}
