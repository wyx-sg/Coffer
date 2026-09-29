// src/components/agents/list/useAgentRowActions.tsx — an agent's one action for its state, its ⋯ menu, and the dialogs they open.
//
// Shared by the Agents list row and the agent detail page (header menu and
// the Overview's own buttons, through `open`), so a state offers the same
// action wherever the agent is shown. Nothing here assumes the list: the row
// is the agent's type row, and `includeOpen` adds the menu's Open item where
// the page is not already the agent's own.
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Copy, Plug, Plus, Power, Unplug, Wrench, type LucideIcon } from "lucide-react";

import {
  AgentConnectionChangeDialog,
  type ConnectionChangeRequest,
} from "@/components/agents/connect/AgentConnectionChangeDialog";
import type { MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import { agentInstallCommand } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useFsActions } from "@/lib/fsActions";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { AgentConfigDirDialog } from "./AgentConfigDirDialog";
import { AgentRemoveDialog } from "./AgentRemoveDialog";
import { useAgentRowState } from "./useAgentRowState";

interface AgentPrimaryAction {
  label: string;
  icon: LucideIcon;
  run: () => void;
  destructive?: boolean;
}

export interface AgentRowActions {
  state: AgentRowState;
  actions: MenuAction[];
  primary: AgentPrimaryAction | null;
  dialogs: ReactNode;
  open: {
    change: (kind: "add" | "connect" | "disconnect") => void;
    configDir: () => void;
    remove: () => void;
    enable: () => void;
  };
}

export function useAgentRowActions(
  row: AgentTypeOut,
  opts: { includeOpen?: boolean } = {},
): AgentRowActions {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const fs = useFsActions();
  const enableMutation = useEnableResource();
  const disableMutation = useDisableResource();
  const { state = "checking", enabled } = useAgentRowState(row);
  const [change, setChange] = useState<ConnectionChangeRequest | null>(null);
  const [configDirOpen, setConfigDirOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const uid = row.uid ?? null;

  const copy = (text: string) =>
    void navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(t("common.copied")))
      .catch(() => undefined);

  const open: AgentRowActions["open"] = {
    change: (kind) => setChange(kind === "add" ? { kind, rows: [row] } : { kind, row }),
    configDir: () => setConfigDirOpen(true),
    remove: () => setRemoveOpen(true),
    enable: () => uid && enableMutation.mutate({ uid, kind: "agent" }),
  };

  let primary: AgentPrimaryAction | null = null;
  switch (state) {
    case "connected":
      primary = {
        label: t("agents.rowMenu.disconnect"),
        icon: Unplug,
        run: () => open.change("disconnect"),
      };
      break;
    case "needs_repair":
      primary = {
        label: t("agents.rowMenu.repair"),
        icon: Wrench,
        run: () => open.change("connect"),
      };
      break;
    case "not_connected":
      primary = {
        label: t("agents.rowMenu.connect"),
        icon: Plug,
        run: () => open.change("connect"),
      };
      break;
    case "not_added":
    case "never_run":
      primary = row.addable
        ? { label: t("agents.rowMenu.add"), icon: Plus, run: () => open.change("add") }
        : null;
      break;
    case "not_installed":
    case "config_left_behind":
      primary = {
        label: t("agents.rowMenu.copyCommand"),
        icon: Copy,
        run: () => copy(agentInstallCommand(row.type)),
      };
      break;
    case "disabled":
      primary = { label: t("agents.rowMenu.enable"), icon: Power, run: open.enable };
      break;
  }

  const dirExists = row.state === "installed_active" || row.state === "config_only";
  const actions: MenuAction[] = [];
  if (opts.includeOpen && uid) {
    actions.push({
      key: "open",
      label: t("agents.rowMenu.open"),
      onSelect: () => navigate(agentTabPath(row.type, "overview")),
    });
  }
  actions.push({
    key: "config-dir",
    label: t("agents.rowMenu.configDir"),
    onSelect: open.configDir,
  });
  if (dirExists) {
    actions.push({
      key: "reveal",
      label: t("agents.rowMenu.reveal"),
      onSelect: () =>
        void fs.reveal(row.config_dir).catch(() => toast.error(t("agents.rowMenu.revealFailed"))),
    });
  }
  if (uid) {
    actions.push({
      key: "copy-uid",
      label: t("agents.rowMenu.copyUid"),
      onSelect: () => copy(uid),
    });
  }
  if (state === "connected" || state === "needs_repair") {
    actions.push({
      key: "disconnect",
      label: t("agents.rowMenu.disconnect"),
      onSelect: () => open.change("disconnect"),
    });
  }
  if (uid) {
    actions.push(
      enabled
        ? {
            key: "disable",
            label: t("agents.rowMenu.disable"),
            onSelect: () => disableMutation.mutate({ uid, kind: "agent" }),
          }
        : { key: "enable", label: t("agents.rowMenu.enable"), onSelect: open.enable },
      {
        key: "remove",
        label: t("agents.rowMenu.remove"),
        destructive: true,
        separated: true,
        onSelect: open.remove,
      },
    );
  }

  const dialogs = (
    <>
      <AgentConnectionChangeDialog request={change} onClose={() => setChange(null)} />
      <AgentConfigDirDialog row={row} open={configDirOpen} onOpenChange={setConfigDirOpen} />
      {uid ? <AgentRemoveDialog row={row} open={removeOpen} onOpenChange={setRemoveOpen} /> : null}
    </>
  );

  return { state, actions, primary, dialogs, open };
}
