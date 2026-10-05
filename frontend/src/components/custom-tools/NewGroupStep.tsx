// src/components/custom-tools/NewGroupStep.tsx — the new group a hand-made request goes into: name,
// description, base URL, headers and default reach. Create group moves on to its first request; nothing is saved until Add.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { agentPrefix } from "@/lib/customTools/groups";
import { isGroupName } from "@/lib/customTools/drafts";
import type { GroupDraft } from "./addFlow";
import { FormField } from "./FormField";
import { GroupDescriptionField } from "./GroupDescriptionField";
import { GroupHeaderRows } from "./GroupHeaderRows";
import { GroupReachField } from "./GroupReachField";
import { useGroupNameError } from "./useGroupNameError";

interface Props {
  group: GroupDraft;
  onGroup: (group: GroupDraft) => void;
  taken: string[];
  onBack: () => void;
  onCancel: () => void;
  onCreate: () => void;
}

export function NewGroupStep({ group, onGroup, taken, ...actions }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const nameError = useGroupNameError(group.name, taken);
  const ready = isGroupName(group.name) && !nameError && group.baseUrl.trim() !== "";

  return (
    <>
      <div className="flex flex-col gap-4">
        <FormField
          label={t("customTools.fields.groupName")}
          htmlFor={`${id}-name`}
          required
          help={t("customTools.fields.groupNameHelp", {
            prefix: agentPrefix(group.name || "name"),
          })}
          error={nameError}
        >
          <Input
            id={`${id}-name`}
            className="font-mono"
            value={group.name}
            aria-invalid={nameError ? true : undefined}
            onChange={(e) => onGroup({ ...group, name: e.target.value.trim() })}
          />
        </FormField>
        <GroupDescriptionField
          value={group.description}
          onChange={(description) => onGroup({ ...group, description })}
        />
        <FormField
          label={t("customTools.fields.baseUrl")}
          htmlFor={`${id}-base`}
          required
          help={t("customTools.fields.baseUrlHelp")}
        >
          <Input
            id={`${id}-base`}
            className="font-mono"
            placeholder="https://"
            value={group.baseUrl}
            onChange={(e) => onGroup({ ...group, baseUrl: e.target.value })}
          />
        </FormField>
        <GroupHeaderRows
          rows={group.headers}
          onChange={(headers) => onGroup({ ...group, headers })}
          help={t("customTools.fields.headersHelp")}
          group={group.name}
        />
        <GroupReachField
          value={group.reach}
          onChange={(reach) => onGroup({ ...group, reach })}
          help={t("customTools.fields.availableToHelp")}
        />
      </div>
      <DialogFooter className="sm:justify-between">
        <Button variant="outline" onClick={actions.onBack}>
          {t("customTools.add.back")}
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={actions.onCancel}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!ready} onClick={actions.onCreate}>
            {t("customTools.newGroup.create")}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
