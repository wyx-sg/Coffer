// src/components/agents/PluginUninstallDialog.tsx — the one "Uninstall <plugin>?" confirmation (board 2.1.33).
//
// Spec agent-registry "Uninstall a plugin by the type's own strategy": Claude
// Code's uninstall runs its own `plugin uninstall` command; Codex's is a config
// edit that drops the plugin's entry from config.toml and deletes its cache.
// The dialog says which of the two is about to happen, and how many skills go
// with the plugin. The caller closes it in the mutation's `onSuccess`, so a
// failed uninstall (toasted by the hook) leaves it open.
import { Trans, useTranslation } from "react-i18next";

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
          <Trans
            i18nKey={
              codex
                ? "agents.pluginsTab.uninstallBody.codex"
                : "agents.pluginsTab.uninstallBody.claude"
            }
            components={{ code: <code className="font-mono text-xs text-text" /> }}
          />
          {skills > 0 ? ` ${t("agents.pluginsTab.uninstallBody.skills", { count: skills })}` : ""}
        </p>
      ) : null}
    </ConfirmDialog>
  );
}
