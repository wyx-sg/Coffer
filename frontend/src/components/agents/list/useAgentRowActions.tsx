// src/components/agents/list/useAgentRowActions.tsx — an agent's one action for its state, its ⋯ menu, and the dialogs they open.
//
// Shared by the Agents list row and the agent detail page (header menu and
// the Overview's own buttons, through `open`), so a state offers the same
// action wherever the agent is shown. Nothing here assumes the list: the row
// is the agent's type row, and `inList` says the menu sits on a list row (whose
// click already opens the agent) rather than on the agent's own page, where an
// agent not found shows Change config directory and Remove as buttons. The
// menu never repeats a visible control: Disconnect and Enable are the row's
// button, the header's or the Overview tab's. An agent whose program is not found
// offers the daemon's install prompt: Copy prompt as its action, and Ask an
// agent in the menu while another managed agent is available.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Plug, Plus, Power, Unplug, Wrench, type LucideIcon } from "lucide-react";

import {
  AgentConnectionChangeDialog,
  type ConnectionChangeRequest,
} from "@/components/agents/connect/AgentConnectionChangeDialog";
import { useAgentHandoff } from "@/components/handoff/useAgentHandoff";
import type { MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useFsActions } from "@/lib/fsActions";
import { useAgentPending, type AgentPending } from "@/lib/hooks/useAgentPending";
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
  /** Long work running on this agent now (connect, disconnect, enable, …), from wherever it started. */
  pending: AgentPending | null;
  open: {
    change: (kind: "add" | "connect" | "disconnect") => void;
    configDir: () => void;
    remove: () => void;
    enable: () => void;
  };
}

export function useAgentRowActions(
  row: AgentTypeOut,
  opts: { inList?: boolean } = {},
): AgentRowActions {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const enableMutation = useEnableResource();
  const disableMutation = useDisableResource();
  const { state = "checking", enabled } = useAgentRowState(row);
  const pending = useAgentPending(row);
  const busy = pending !== null;
  const [change, setChange] = useState<ConnectionChangeRequest | null>(null);
  const [configDirOpen, setConfigDirOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const uid = row.uid ?? null;
  const installPrompt = row.install_handoff?.prompt ?? null;
  const handoff = useAgentHandoff(installPrompt ?? "");

  const copy = (text: string) =>
    void navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(t("common.copied")))
      .catch(() => undefined);

  const open: AgentRowActions["open"] = {
    change: (kind) => setChange(kind === "add" ? { kind, rows: [row] } : { kind, row }),
    configDir: () => setConfigDirOpen(true),
    remove: () => setRemoveOpen(true),
    enable: () => uid && !busy && enableMutation.mutate({ uid, kind: "agent" }),
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
      primary = installPrompt
        ? {
            label: t("handoff.copyPrompt"),
            icon: Copy,
            run: () => copy(installPrompt),
          }
        : null;
      break;
    case "disabled":
      primary = { label: t("agents.rowMenu.enable"), icon: Power, run: open.enable };
      break;
  }

  const dirExists = row.state === "installed_active" || row.state === "config_only";
  const actions: MenuAction[] = [];
  if (installPrompt && handoff.canAsk) {
    actions.push({ key: "ask-agent", label: t("handoff.askAgent"), onSelect: handoff.ask });
  }
  // On the page of an agent not found, the card offers these two as buttons.
  const cardHasThem = state === "not_found" && !opts.inList;
  if (!cardHasThem) {
    actions.push({
      key: "config-dir",
      label: t("agents.rowMenu.configDir"),
      onSelect: open.configDir,
      disabled: busy,
    });
  }
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
  // A connected agent's Disconnect is already a button (the row's, or the Overview's).
  if (state === "needs_repair") {
    actions.push({
      key: "disconnect",
      label: t("agents.rowMenu.disconnect"),
      onSelect: () => open.change("disconnect"),
      disabled: busy,
    });
  }
  if (uid) {
    // A disabled agent's Enable is the row's / header's button; Turn off only
    // while it is on.
    if (enabled) {
      actions.push({
        key: "disable",
        label: t("agents.rowMenu.disable"),
        onSelect: () => disableMutation.mutate({ uid, kind: "agent" }),
        disabled: busy,
      });
    } else if (state !== "disabled") {
      actions.push({
        key: "enable",
        label: t("agents.rowMenu.enable"),
        onSelect: open.enable,
        disabled: busy,
      });
    }
    if (!cardHasThem) {
      actions.push({
        key: "remove",
        label: t("agents.rowMenu.remove"),
        destructive: true,
        separated: true,
        onSelect: open.remove,
        disabled: busy,
      });
    }
  }

  const dialogs = (
    <>
      <AgentConnectionChangeDialog request={change} onClose={() => setChange(null)} />
      <AgentConfigDirDialog row={row} open={configDirOpen} onOpenChange={setConfigDirOpen} />
      {uid ? <AgentRemoveDialog row={row} open={removeOpen} onOpenChange={setRemoveOpen} /> : null}
    </>
  );

  return { state, actions, primary, dialogs, pending, open };
}
