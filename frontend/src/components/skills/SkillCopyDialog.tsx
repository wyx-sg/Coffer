// frontend/src/components/skills/SkillCopyDialog.tsx
// "frontend-design: a folder is in the way in Codex" (canvas 4.3.28, 4.3.26,
// 4.3.27): an agent's link path holds a real folder, not Coffer's link, and
// Coffer left it alone. The 1060 two-way choice (spec skill-manager "Resolve a
// folder in the way of a skill's link"):
//   Replace it with Coffer's link — the folder is moved to ~/.coffer/backup/
//     first, then the master is linked in its place;
//   Adopt this folder — its files become the master, so every other agent
//     gets them too.
// Under the cards, what happens to each agent; on the right the diff of the side
// you are not keeping. The primary names the write; nothing is written before it.
// Which one to keep is the person's call, so there is no hand-off here.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { Skeleton } from "@/components/ui/skeleton";
import { DialogErrorBanner } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import type { ChangeItem, ChangeSummaryLine } from "@/lib/changePreview/changeCounts";
import type { SkillDriftEntry, SkillFileChange, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useResolveSkillCopy, useSkillCopyCompare } from "@/lib/hooks/useSkillCopies";
import { joinNames } from "@/lib/skills/names";
import { SkillChoiceDialog } from "./SkillChoiceDialog";
import { CHANGE_OP, parseUnifiedDiff, reverseChange } from "./skillSourceHelpers";

interface Props {
  skill: SkillOut;
  /** The finding under review; null closes the dialog. */
  entry: SkillDriftEntry | null;
  onOpenChange: (open: boolean) => void;
}

type Keep = "master" | "agent";

function item(
  change: SkillFileChange,
  path: string,
  agent: { type: string; name?: string },
): ChangeItem {
  return {
    id: path,
    agentType: agent.type,
    agentName: agent.name,
    path,
    op: CHANGE_OP[change.status],
    added: change.additions,
    removed: change.deletions,
    diff: change.binary ? [] : parseUnifiedDiff(change.diff),
  };
}

export function SkillCopyDialog({ skill, entry, onOpenChange }: Props) {
  const { t, i18n } = useTranslation();
  const { data: agents = [] } = useAgents();
  const agent = entry ? agents.find((a) => a.name === entry.agent_name) : undefined;
  const compare = useSkillCopyCompare(skill.uid, agent?.uid ?? null);
  const resolve = useResolveSkillCopy();
  const [keep, setKeep] = useState<Keep>("master");
  useEffect(() => {
    setKeep("master");
    resolve.reset();
    // Reset per finding only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry?.agent_name, entry?.skill_name]);

  const agentName = agent?.display_name ?? entry?.agent_name ?? "";
  const path = abbreviateHomePath(compare.data?.path ?? entry?.target_path ?? "");
  const others = skill.bindings.filter((b) => b.agent_uid !== agent?.uid);
  const otherNames = others.map(
    (b) => agents.find((a) => a.uid === b.agent_uid)?.display_name ?? b.agent_name,
  );
  const agentRef = { type: agent?.type ?? "", name: agentName };

  // The diff is the change to the side that is not kept.
  const items = (compare.data?.changes ?? []).map((c) =>
    keep === "master"
      ? item(reverseChange(c), `${path}/${c.path}`, agentRef)
      : item(c, t("skills.copy.inCoffer", { path: `${skill.name}/${c.path}` }), { type: "coffer" }),
  );

  const othersLine = (text: string): ChangeSummaryLine[] =>
    others.map((b) => {
      const a = agents.find((x) => x.uid === b.agent_uid);
      return { agentType: a?.type ?? "", agentName: a?.display_name ?? b.agent_name, text };
    });
  const agentLine = (text: string): ChangeSummaryLine => ({
    agentType: agentRef.type,
    agentName: agentRef.name,
    text,
  });
  const happen: ChangeSummaryLine[] =
    keep === "master"
      ? [
          agentLine(t("skills.copy.happenMasterAgent", { name: skill.name })),
          ...othersLine(t("skills.copy.happenMasterOthers")),
        ]
      : [
          {
            agentType: "coffer",
            agentName: "Coffer",
            text: t("skills.copy.happenAgentCoffer", { name: skill.name, agent: agentName }),
          },
          ...othersLine(t("skills.copy.happenAgentOthers")),
          agentLine(t("skills.copy.happenAgentAgent")),
        ];

  const apply = () => {
    if (!agent) return;
    resolve.mutate(
      { uid: skill.uid, agentUid: agent.uid, keep },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <SkillChoiceDialog<Keep>
      open={entry !== null}
      onOpenChange={onOpenChange}
      title={
        <>
          <span className="font-mono text-md">{skill.name}</span>
          {t("skills.copy.title", { agent: agentName })}
        </>
      }
      subtitle={t("skills.copy.subtitle", { path })}
      groupLabel={t("skills.copy.choiceLabel")}
      choices={[
        {
          value: "master",
          title: t("skills.copy.master"),
          help: t("skills.copy.masterHelp"),
        },
        {
          value: "agent",
          title: t("skills.copy.agent"),
          help:
            otherNames.length > 0
              ? t("skills.copy.agentHelp", {
                  count: otherNames.length,
                  agents: joinNames(otherNames, i18n.language),
                })
              : t("skills.copy.agentHelpAlone"),
        },
      ]}
      value={keep}
      onChange={setKeep}
      happen={happen}
      confirmLabel={
        keep === "master" ? t("skills.copy.confirmMaster") : t("skills.copy.confirmAgent")
      }
      onConfirm={apply}
      confirmDisabled={!agent || !!compare.error}
      pending={resolve.isPending}
      error={
        resolve.error ? (
          <DialogErrorBanner
            title={t("skills.copy.failed")}
            message={translateApiError(t, resolve.error)}
          />
        ) : null
      }
    >
      {compare.isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : compare.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, compare.error)}
        </p>
      ) : items.length === 0 ? (
        <p className="text-xs text-text-muted">{t("skills.copy.same")}</p>
      ) : (
        <>
          {items.map((it) => (
            <FileDiff key={it.id} item={it} />
          ))}
          <p className="text-xs text-text-muted">
            {keep === "master"
              ? t("skills.copy.captionMaster", { agent: agentName })
              : t("skills.copy.captionAgent", { agent: agentName })}
          </p>
        </>
      )}
    </SkillChoiceDialog>
  );
}
