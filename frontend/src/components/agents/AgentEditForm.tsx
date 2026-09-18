// frontend/src/components/agents/AgentEditForm.tsx — spec agent-registry
// User Story 4 / FR-006: edit an existing agent's name, config_dir override and
// description. Rendered as a modal dialog (mirrors AgentAddDialog); the agent's
// TYPE is immutable post-registration and shows read-only.
//
// The NAME is editable. It was read-only because it was the agent's identity —
// everything that pointed at this agent spelled it — and now it is a label like
// any other, so it is edited like any other. It travels through a different
// request from the rest of the form, though: renaming is the kind-agnostic
// `PATCH /resources/{uid}` that every kind renames through, while `config_dir`
// and `description` are the agent kind's own PATCH. Both are sent, in that
// order, and a 409 on the name shows up next to the field the user typed it in.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FolderPickerField } from "@/components/agents/FolderPickerField";
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
import { useRenameResource } from "@/lib/hooks/useResourceMutations";

export function AgentEditForm(props: {
  agent: AgentOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const patch = usePatchAgent();
  const rename = useRenameResource();
  // Initialise inputs from the existing record so the user sees what is
  // currently set; the folder the user picks IS the config dir.
  const [name, setName] = useState<string>(props.agent.name);
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
    const newName = name.trim();
    const renamed = newName !== "" && newName !== props.agent.name;
    if (!renamed && Object.keys(body).length === 0) {
      props.onClose();
      return;
    }
    try {
      // The rename goes FIRST: it is the one write that can be refused for a
      // reason the user has to fix (the label is taken), and a refusal has to
      // leave the rest of the form unapplied rather than half-applied.
      if (renamed) {
        await rename.mutateAsync({ kind: "agent", uid: props.agent.uid, name: newName });
      }
      if (Object.keys(body).length > 0) {
        await patch.mutateAsync({ uid: props.agent.uid, body });
      }
      props.onSaved();
    } catch {
      // Error surfaced via `patch.error` / `rename.error` below.
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
          <div className="space-y-1.5">
            <Label htmlFor="agent-edit-name">{t("agents.name")}</Label>
            <Input
              id="agent-edit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("agents.namePlaceholder")}
            />
          </div>
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
          <div className="space-y-1.5">
            <Label htmlFor="agent-edit-description">{t("agents.description")}</Label>
            <Input
              id="agent-edit-description"
              placeholder={t("agents.descriptionPlaceholder")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {rename.error || patch.error ? (
            <p role="alert" className="text-sm text-destructive">
              {translateApiError(t, rename.error ?? patch.error)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={patch.isPending || rename.isPending}>
              {patch.isPending || rename.isPending ? t("common.saving") : t("agents.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
