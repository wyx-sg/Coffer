// src/components/custom-tools/NewGroupStep.tsx — the new group a hand-made request goes into: name, base URL,
// auth and default reach. Its tools are added after, one request at a time.
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { agentPrefix } from "@/lib/customTools/groups";
import { isGroupName } from "@/lib/customTools/drafts";
import type { GroupDraft } from "./addFlow";
import { AuthFields } from "./AuthFields";
import { DraftReachField } from "./DraftReachField";
import { FormField } from "./FormField";

interface Props {
  group: GroupDraft;
  onGroup: (group: GroupDraft) => void;
  taken: string[];
  creating: boolean;
  error: unknown;
  onBack: () => void;
  onCancel: () => void;
  onCreate: () => void;
}

export function NewGroupStep({ group, onGroup, taken, creating, error, ...actions }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const nameTaken = taken.includes(group.name);
  const nameError =
    group.name && !isGroupName(group.name)
      ? t("customTools.add.nameInvalid")
      : nameTaken
        ? t("customTools.add.nameTaken")
        : undefined;
  const ready = isGroupName(group.name) && !nameTaken && group.baseUrl.trim() !== "";

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
        <AuthFields value={group.auth} onChange={(auth) => onGroup({ ...group, auth })} />
        <FormField
          label={t("customTools.fields.availableTo")}
          help={t("customTools.fields.availableToHelp")}
        >
          <DraftReachField
            value={group.agents}
            onChange={(agents) => onGroup({ ...group, agents })}
            defaultLabel={t("scope.everywhere")}
            defaultSub={t("scope.everywhereSub")}
          />
        </FormField>
        {error ? (
          <div role="alert" className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{translateApiError(t, error)}</span>
          </div>
        ) : null}
      </div>
      <DialogFooter className="sm:justify-between">
        <Button variant="ghost" onClick={actions.onBack}>
          {t("customTools.add.back")}
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={actions.onCancel}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!ready || creating} onClick={actions.onCreate}>
            {t("customTools.newGroup.create")}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
