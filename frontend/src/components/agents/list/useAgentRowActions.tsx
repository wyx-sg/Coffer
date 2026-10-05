// src/components/agents/list/useAgentRowActions.tsx — an agent's one visible action for its state, its ⋯ menu, and the dialogs they open.
//
// Shared by the Agents list row and the agent detail page (header menu and
// the Overview's own buttons, through `open`), so a state offers the same
// action wherever the agent is shown. The visible button is only ever a fix
// Coffer can make: Connect (not connected, or a newly found agent), or Repair.
// A healthy row has none. An agent whose program is not on this Mac has no fix
// Coffer can make: it gets `handoff`, the daemon's install prompt, which the list
// row shows as the shared Hand off to <Agent> split button (Foundations 0.7.04) before
// the ⋯; the detail page shows it in the Overview instead. The menu never
// repeats a visible action. Connect, Repair and
// Disconnect all open the Review changes dialog; a connected agent's config
// directory moves through its own review. There is no Remove: the list always
// holds both supported agents.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Plug, Wrench, type LucideIcon } from "lucide-react";

import {
  AgentConnectionChangeDialog,
  type ConnectionChangeRequest,
} from "@/components/agents/connect/AgentConnectionChangeDialog";
import type { MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useFsActions } from "@/lib/fsActions";
import { useAgentPending, type AgentPending } from "@/lib/hooks/useAgentPending";
import { AgentConfigDirDialog } from "./AgentConfigDirDialog";
import { useAgentRowState } from "./useAgentRowState";
import { useRowDialogState } from "./useRowDialogState";

interface AgentPrimaryAction {
  label: string;
  icon: LucideIcon;
  run: () => void;
}

export interface AgentRowActions {
  state: AgentRowState;
  actions: MenuAction[];
  primary: AgentPrimaryAction | null;
  /** The install prompt of an agent whose program is not on this Mac, handed off visibly. */
  handoff: string | null;
  dialogs: ReactNode;
  /** Long work running on this agent now (connect, disconnect, …), from wherever it started. */
  pending: AgentPending | null;
  open: {
    change: (kind: "add" | "connect" | "disconnect") => void;
    configDir: () => void;
  };
}

export function useAgentRowActions(
  row: AgentTypeOut,
  opts: { inList?: boolean } = {},
): AgentRowActions {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const { state = "checking", connection } = useAgentRowState(row);
  const pending = useAgentPending(row);
  const busy = pending !== null;
  const [change, setChange] = useRowDialogState<ConnectionChangeRequest | null>(
    `${row.type}:change`,
    null,
  );
  const [configDirOpen, setConfigDirOpen] = useRowDialogState(`${row.type}:configDir`, false);
  const uid = row.uid ?? null;
  const installPrompt = row.install_handoff?.prompt ?? null;

  const copy = (text: string) =>
    void navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(t("common.copied")))
      .catch(() => undefined);

  const open: AgentRowActions["open"] = {
    change: (kind) => setChange(kind === "add" ? { kind, rows: [row] } : { kind, row }),
    configDir: () => setConfigDirOpen(true),
  };

  let primary: AgentPrimaryAction | null = null;
  switch (state) {
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
    // A newly found agent is the same off state: Connect registers it, then connects it.
    case "not_added":
    case "never_run":
      primary = row.addable
        ? { label: t("agents.rowMenu.connect"), icon: Plug, run: () => open.change("add") }
        : null;
      break;
  }

  const dirExists = row.state === "installed_active" || row.state === "config_only";
  const installRow = state === "not_installed" || state === "config_left_behind";
  const handoff = installRow ? installPrompt : null;
  const actions: MenuAction[] = [];
  // On the page of an agent not found, the card offers the directory change as a button.
  const cardHasIt = state === "not_found" && !opts.inList;
  if (!cardHasIt) {
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
  // Disconnect is never a visible button: the entry and hook come out through Review changes.
  const hasParts = !!connection?.parts.some((p) => p.installed);
  if (uid && hasParts) {
    actions.push({
      key: "disconnect",
      label: t("agents.rowMenu.disconnect"),
      onSelect: () => open.change("disconnect"),
      disabled: busy,
    });
  }

  const dialogs = (
    <>
      <AgentConnectionChangeDialog request={change} onClose={() => setChange(null)} />
      <AgentConfigDirDialog row={row} open={configDirOpen} onOpenChange={setConfigDirOpen} />
    </>
  );

  return { state, actions, primary, handoff, dialogs, pending, open };
}
