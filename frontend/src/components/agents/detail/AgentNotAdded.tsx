// src/components/agents/detail/AgentNotAdded.tsx — the page of a supported type with no agent added yet.
//
// An addable type (installed, run or not) offers Add — the same preview as the
// list row's. One that cannot be added says why and how to fix it: the
// command that installs (or reinstalls) its program, to copy.
import { useTranslation } from "react-i18next";
import { Bot, Copy, Plus } from "lucide-react";

import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath, agentInstallCommand, agentTypeLabel } from "@/lib/agents/display";
import { isAddableState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";

interface Props {
  typeRow: AgentTypeOut;
  rowActions: ReturnType<typeof useAgentRowActions>;
}

export function AgentNotAdded({ typeRow, rowActions }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const name = agentTypeLabel(typeRow.type);
  const command = agentInstallCommand(typeRow.type);

  if (typeRow.addable && isAddableState(rowActions.state)) {
    return (
      <EmptyState
        icon={Bot}
        title={t("agents.detail.notAdded.title", { name })}
        description={t("agents.detail.notAdded.body", {
          name,
          dir: abbreviateHomePath(typeRow.config_dir),
        })}
        action={
          <Button size="sm" onClick={() => rowActions.open.change("add")}>
            <Plus aria-hidden className="size-3.5" />
            {t("agents.detail.add")}
          </Button>
        }
      />
    );
  }

  const copy = () =>
    void navigator.clipboard
      ?.writeText(command)
      .then(() => toast.success(t("common.copied")))
      .catch(() => undefined);

  const leftBehind = typeRow.state === "config_only";
  return (
    <EmptyState
      icon={Bot}
      title={t(leftBehind ? "agents.detail.leftBehind.title" : "agents.detail.notInstalled.title", {
        name,
      })}
      description={t(
        leftBehind ? "agents.detail.leftBehind.body" : "agents.detail.notInstalled.body",
        { name, dir: abbreviateHomePath(typeRow.config_dir), command },
      )}
      action={
        <Button variant="outline" size="sm" onClick={copy}>
          <Copy aria-hidden className="size-3.5" />
          {t("agents.detail.copyCommand")}
        </Button>
      }
    />
  );
}
