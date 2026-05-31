// frontend/src/components/agents/AgentEditForm.tsx — spec 004-agent-registry
// User Story 4 / FR-006: edit an existing agent's config_dir override and
// description. Rendered as a modal dialog (mirrors AgentAddDialog); the agent
// name and type are immutable post-registration so they show read-only.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FolderPicker } from "@/components/agents/FolderPicker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AgentOut, AgentPatch } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { usePatchAgent } from "@/lib/hooks/useAgents";

export function AgentEditForm(props: {
  agent: AgentOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const patch = usePatchAgent();
  // Initialise inputs from the existing record so the user sees what is
  // currently set; the folder the user picks IS the config dir.
  const [configDir, setConfigDir] = useState<string>(props.agent.config_dir ?? "");
  const [description, setDescription] = useState<string>(props.agent.description ?? "");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Build a diff-shaped PATCH body. We only include fields the user
    // actually changed; this lets the server preserve unrelated fields
    // (and exercises the description-only PATCH fix in CODE25-008).
    const body: AgentPatch = {};
    const newConfigDir = configDir.trim() === "" ? null : configDir;
    if (newConfigDir !== (props.agent.config_dir ?? null)) {
      body.config_dir = newConfigDir;
    }
    const newDescription = description.trim() === "" ? null : description;
    if (newDescription !== (props.agent.description ?? null)) {
      body.description = newDescription;
    }
    if (Object.keys(body).length === 0) {
      props.onClose();
      return;
    }
    try {
      await patch.mutateAsync({ name: props.agent.name, body });
      props.onSaved();
    } catch {
      // Error surfaced via `patch.error` below; nothing else to do.
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) props.onClose();
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("agents.editTitle")}</DialogTitle>
          <DialogDescription>{t("agents.editSubtitle")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            {t("agents.name")}
            <input
              className="mt-1 block w-full rounded border bg-muted px-2 py-1"
              value={props.agent.name}
              disabled
              readOnly
            />
          </label>
          <label className="block text-sm">
            {t("agents.type")}
            <input
              className="mt-1 block w-full rounded border bg-muted px-2 py-1"
              value={props.agent.type}
              disabled
              readOnly
            />
          </label>
          <div className="block text-sm">
            <span>{t("agents.configDirOverride")}</span>
            <div className="mt-1 flex gap-2">
              <input
                aria-label={t("agents.configDirOverride")}
                className="block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
                placeholder={t("agents.configDirPlaceholder")}
                value={configDir}
                onChange={(e) => setConfigDir(e.target.value)}
              />
              <FolderPicker value={configDir || null} onChange={(p) => setConfigDir(p ?? "")} />
            </div>
          </div>
          <label className="block text-sm">
            {t("agents.description")}
            <input
              className="mt-1 block w-full rounded border bg-background px-2 py-1"
              placeholder={t("agents.descriptionPlaceholder")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          {patch.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, patch.error)}</p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={patch.isPending}>
              {patch.isPending ? t("common.saving") : t("agents.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
