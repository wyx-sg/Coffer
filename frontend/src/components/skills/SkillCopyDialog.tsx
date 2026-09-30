// frontend/src/components/skills/SkillCopyDialog.tsx
// "A folder is in the way in Codex" (canvas 4.3.23, 4.3.24, 4.3.41): an
// agent's link path holds a real folder, not Coffer's link, and Coffer left
// it alone. The dialog compares the two sides and offers two confirmed
// choices (spec skill-manager "Resolve a folder in the way of a skill's
// link"):
//   Replace it with Coffer's link — the folder is moved to ~/.coffer/content/backup/
//     first, then the master is linked in its place;
//   Adopt this folder — its files become the master, so every other agent
//     gets them too.
// The diff shows what happens to the side the reader is not keeping. The
// finding's hand-off asks an agent to compare the two and advise; the choice
// stays these two buttons.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { SkillChoiceCards } from "@/components/skills/SkillChoiceCards";
import { SkillUpdateDiff } from "@/components/skills/SkillUpdateDiff";
import { reverseChange } from "@/components/skills/skillSourceHelpers";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useResolveSkillCopy, useSkillCopyCompare } from "@/lib/hooks/useSkillCopies";
import { joinNames } from "@/lib/skills/names";

interface Props {
  skill: SkillOut;
  /** The finding under review; null closes the dialog. */
  entry: SkillDriftEntry | null;
  onOpenChange: (open: boolean) => void;
}

type Keep = "master" | "agent";

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
  const others = skill.bindings
    .filter((b) => b.agent_uid !== agent?.uid)
    .map((b) => agents.find((a) => a.uid === b.agent_uid)?.display_name ?? b.agent_name);
  const changes = (compare.data?.changes ?? []).map((c) =>
    keep === "master"
      ? { ...reverseChange(c), path: `${path}/${c.path}` }
      : { ...c, path: t("skills.copy.inCoffer", { path: `${skill.name}/${c.path}` }) },
  );

  const apply = () => {
    if (!agent) return;
    resolve.mutate(
      { uid: skill.uid, agentUid: agent.uid, keep },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={entry !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100vh-4rem)] max-w-[760px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="mb-0 shrink-0 gap-[3px] pb-3 pl-5 pr-12 pt-4">
          <DialogTitle>
            <span className="font-mono">{skill.name}</span>
            {t("skills.copy.title", { agent: agentName })}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {t("skills.copy.subtitle", { path })}
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
          <SkillChoiceCards<Keep>
            label={t("skills.copy.choiceLabel")}
            value={keep}
            onChange={setKeep}
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
                  others.length > 0
                    ? t("skills.copy.agentHelp", {
                        count: others.length,
                        agents: joinNames(others, i18n.language),
                      })
                    : t("skills.copy.agentHelpAlone"),
              },
            ]}
          />
          {entry?.handoff ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="text-xs text-text-muted">{t("skills.copy.askAgent")}</span>
              <AgentHandoff prompt={entry.handoff.prompt} size="sm" />
            </div>
          ) : null}
          {compare.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : compare.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, compare.error)}
            </p>
          ) : changes.length === 0 ? (
            <p className="text-xs text-text-muted">{t("skills.copy.same")}</p>
          ) : (
            changes.map((c) => <SkillUpdateDiff key={c.path} change={c} />)
          )}
          {resolve.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, resolve.error)}
            </p>
          ) : null}
        </div>
        <DialogFooter className="m-0 mt-0 flex-row items-center justify-start gap-2 rounded-none px-5 py-3 sm:justify-start">
          <span className="min-w-0 text-xs text-text-muted">{t("skills.copy.note")}</span>
          <span className="ml-auto flex shrink-0 gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!agent || !!compare.error || resolve.isPending} onClick={apply}>
              {keep === "master"
                ? t("skills.copy.confirmMaster")
                : t("skills.copy.confirmAgent", { name: skill.name })}
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
