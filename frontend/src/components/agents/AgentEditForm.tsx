// frontend/src/components/agents/AgentEditForm.tsx — spec agent-registry
// "Manage the agent lifecycle": edit an existing agent's config directory.
// Rendered as a modal dialog (mirrors AgentAddDialog). An agent is one per type
// per machine and is named by its type, so the name and the TYPE are both
// fixed; the type shows read-only for context.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FolderPickerField } from "@/components/FolderPickerField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AgentOut, AgentPatch } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { agentTypeLabel } from "@/lib/agents/display";
import { usePatchAgent } from "@/lib/hooks/useAgents";

export function AgentEditForm(props: {
  agent: AgentOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const patch = usePatchAgent();
  // Initialise from the existing record so the user sees what is currently
  // set; the folder the user picks IS the config dir.
  const [configDir, setConfigDir] = useState<string>(props.agent.config_dir ?? "");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Diff-shaped PATCH body: only a field the user actually changed is sent,
    // so the server preserves the rest.
    const body: AgentPatch = {};
    const newConfigDir = configDir.trim() === "" ? null : configDir;
    if (newConfigDir !== (props.agent.config_dir ?? null)) {
      body.config_dir = newConfigDir;
    }
    if (Object.keys(body).length === 0) {
      props.onClose();
      return;
    }
    try {
      await patch.mutateAsync({ uid: props.agent.uid, body });
      props.onSaved();
    } catch {
      // Error surfaced via `patch.error` below.
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) props.onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("agents.editTitle")}</DialogTitle>
          <DialogDescription>{t("agents.editSubtitle")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="agent-edit-type">{t("agents.type")}</Label>
            <Input
              id="agent-edit-type"
              value={agentTypeLabel(props.agent.type)}
              disabled
              readOnly
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("agents.configDirOverride")}</Label>
            <FolderPickerField
              ariaLabel={t("agents.configDirOverride")}
              placeholder={t("agents.configDirPlaceholder")}
              value={configDir || null}
              onChange={(p) => setConfigDir(p ?? "")}
              clearable
            />
          </div>
          {patch.error ? (
            <p role="alert" className="text-sm text-destructive">
              {translateApiError(t, patch.error)}
            </p>
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
