// src/components/agents/PluginUninstallDialog.tsx — the one "Uninstall <plugin>?" confirmation, tab and plugin page alike.
//
// Spec agent-registry "Uninstall a plugin by the type's own strategy": Claude
// Code's uninstall runs its own `claude plugin uninstall <id>`; Codex's is a
// config edit that drops the plugin's entry from config.toml and deletes its
// cache. The dialog says which of the two is about to happen, and that the
// skills the plugin bundles go with it. The caller closes it in the
// mutation's `onSuccess`, so a failed uninstall (toasted by the hook) leaves it open.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { PluginOut } from "@/lib/api/agents-workspace";

interface Props {
  agentType: string;
  /** The plugin to uninstall; the dialog is open while one is set. */
  plugin: PluginOut | null;
  onClose: () => void;
  pending: boolean;
  onConfirm: (plugin: PluginOut) => void;
}

export function PluginUninstallDialog({ agentType, plugin, onClose, pending, onConfirm }: Props) {
  const { t } = useTranslation();
  const codex = agentType === "codex";
  const skills = plugin?.skills.length ?? 0;
  return (
    <ConfirmDialog
      open={plugin !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t("agents.pluginsTab.uninstallTitle", { name: plugin?.name ?? "" })}
      confirmLabel={t("agents.pluginsTab.uninstall")}
      pending={pending}
      onConfirm={() => {
        if (plugin) onConfirm(plugin);
      }}
    >
      {plugin ? (
        <p className="text-sm text-text-muted">
          {codex
            ? t("agents.pluginsTab.uninstallBody.codex")
            : t("agents.pluginsTab.uninstallBody.claudeLead")}{" "}
          <code className="break-all font-mono text-xs text-text">
            {codex ? `[plugins."${plugin.id}"]` : `claude plugin uninstall ${plugin.id}`}
          </code>
          {codex
            ? t("agents.pluginsTab.uninstallBody.codexTail")
            : t("agents.pluginsTab.uninstallBody.claudeTail")}
          {skills > 0 ? ` ${t("agents.pluginsTab.uninstallBody.skills", { count: skills })}` : ""}
        </p>
      ) : null}
    </ConfirmDialog>
  );
}
