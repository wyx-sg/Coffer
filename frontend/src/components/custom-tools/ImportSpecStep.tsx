// src/components/custom-tools/ImportSpecStep.tsx — Import step 1 of 2: the group, the spec, and what the spec prefills.
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { OpenApiReading } from "@/lib/api/customTools";
import { agentPrefix } from "@/lib/customTools/groups";
import { isGroupName } from "@/lib/customTools/drafts";
import { useReadOpenApi } from "@/lib/hooks/useCustomTools";
import { defaultPicks, type GroupDraft, type ImportDraft } from "./addFlow";
import { AuthFields } from "./AuthFields";
import { DraftReachField } from "./DraftReachField";
import { FormField } from "./FormField";
import { SpecField } from "./SpecField";

interface Props {
  group: GroupDraft;
  onGroup: (group: GroupDraft) => void;
  spec: ImportDraft;
  onSpec: (spec: ImportDraft) => void;
  taken: string[];
  onCancel: () => void;
  onNext: () => void;
}

export function ImportSpecStep({ group, onGroup, spec, onSpec, taken, onCancel, onNext }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const read = useReadOpenApi();
  const [tooLarge, setTooLarge] = useState(false);
  const [fromSpec, setFromSpec] = useState(false);

  const loaded = (reading: OpenApiReading, patch: Partial<ImportDraft>) => {
    onSpec({ ...spec, ...patch, reading, picked: defaultPicks(reading) });
    onGroup({
      ...group,
      baseUrl: reading.base_url ?? group.baseUrl,
      auth: reading.auth_header
        ? { ...group.auth, header: reading.auth_header, prefix: reading.auth_prefix.trim() }
        : group.auth,
    });
    setFromSpec(Boolean(reading.auth_header));
  };
  const loadUrl = () => {
    setTooLarge(false);
    read.mutate({ url: spec.url.trim() }, { onSuccess: (r) => loaded(r, {}) });
  };
  const loadFile = (fileName: string, document: string) => {
    setTooLarge(false);
    onSpec({ ...spec, fileName, document, reading: null });
    read.mutate(
      { document, filename: fileName },
      { onSuccess: (r) => loaded(r, { fileName, document }) },
    );
  };

  const nameTaken = taken.includes(group.name);
  const nameError =
    group.name && !isGroupName(group.name)
      ? t("customTools.add.nameInvalid")
      : nameTaken
        ? t("customTools.add.nameTaken")
        : undefined;
  const ready = isGroupName(group.name) && !nameTaken && spec.reading !== null && !read.isPending;
  const specError = tooLarge ? new Error(t("customTools.import.tooLarge")) : read.error;

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
        <SpecField
          mode={spec.mode}
          onMode={(mode) => onSpec({ ...spec, mode })}
          url={spec.url}
          onUrl={(url) => onSpec({ ...spec, url })}
          fileName={spec.fileName}
          onLoad={loadUrl}
          onFile={loadFile}
          onFileTooLarge={() => setTooLarge(true)}
          loading={read.isPending}
          reading={spec.reading}
          error={specError}
        />
        <FormField
          label={t("customTools.fields.baseUrl")}
          htmlFor={`${id}-base`}
          help={t("customTools.fields.baseUrlHelp")}
        >
          <Input
            id={`${id}-base`}
            className="font-mono"
            value={group.baseUrl}
            onChange={(e) => onGroup({ ...group, baseUrl: e.target.value })}
          />
        </FormField>
        <AuthFields
          value={group.auth}
          onChange={(auth) => onGroup({ ...group, auth })}
          headerHelp={fromSpec ? t("customTools.import.authFromSpec") : undefined}
        />
        <FormField label={t("customTools.fields.availableTo")}>
          <DraftReachField
            value={group.agents}
            onChange={(agents) => onGroup({ ...group, agents })}
            defaultLabel={t("scope.everywhere")}
            defaultSub={t("scope.everywhereSub")}
          />
        </FormField>
      </div>
      <DialogFooter>
        <Button variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!ready || group.baseUrl.trim() === ""} onClick={onNext}>
          {t("customTools.import.review")}
        </Button>
      </DialogFooter>
    </>
  );
}
