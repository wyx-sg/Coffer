// src/components/custom-tools/ImportSpecStep.tsx — Import step 1 of 2: the new group's name, the spec, the
// operations to turn into tools, and the auth, secret and reach the spec prefills.
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { OpenApiReading } from "@/lib/api/customTools";
import { agentPrefix } from "@/lib/customTools/groups";
import { isGroupName } from "@/lib/customTools/drafts";
import { useReadOpenApi } from "@/lib/hooks/useCustomTools";
import { defaultPicks, headerRowsFromSpec, type GroupDraft, type ImportDraft } from "./addFlow";
import { FormField } from "./FormField";
import { GroupHeaderRows } from "./GroupHeaderRows";
import { GroupReachField } from "./GroupReachField";
import { OperationPicker } from "./OperationPicker";
import { SpecField } from "./SpecField";
import { TryOperation } from "./TryOperation";
import { useGroupNameError } from "./useGroupNameError";
import { WaySummary } from "./WaySummary";

interface Props {
  group: GroupDraft;
  onGroup: (group: GroupDraft) => void;
  spec: ImportDraft;
  onSpec: (spec: ImportDraft) => void;
  taken: string[];
  onChangeWay: () => void;
  onCancel: () => void;
  onNext: () => void;
}

export function ImportSpecStep(props: Props) {
  const { group, onGroup, spec, onSpec } = props;
  const { t } = useTranslation();
  const id = useId();
  const read = useReadOpenApi();
  const [tooLarge, setTooLarge] = useState(false);
  const [trying, setTrying] = useState(false);

  const loaded = (reading: OpenApiReading, patch: Partial<ImportDraft>) => {
    onSpec({ ...spec, ...patch, reading, picked: defaultPicks(reading) });
    onGroup({
      ...group,
      baseUrl: reading.base_url ?? group.baseUrl,
      // The spec's security scheme names one header; a row of the person's own stays.
      headers: group.headers.length > 0 ? group.headers : headerRowsFromSpec(reading.auth_header),
    });
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

  const nameError = useGroupNameError(group.name, props.taken);
  const reading = read.isPending || read.error ? null : spec.reading;
  const ready =
    isGroupName(group.name) && !nameError && reading !== null && group.baseUrl.trim() !== "";
  const specError = tooLarge ? new Error(t("customTools.import.tooLarge")) : read.error;

  return (
    <>
      <div className="flex flex-col gap-4">
        <WaySummary
          way="import"
          newGroup
          sub={t("customTools.add.importSummary")}
          onChange={props.onChangeWay}
        />
        <FormField
          label={t("customTools.fields.groupName")}
          htmlFor={`${id}-name`}
          required
          help={t("customTools.import.groupNameHelp", {
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
          fileText={spec.mode === "file" ? spec.document : undefined}
        />
        {reading ? (
          <>
            <OperationPicker
              reading={reading}
              picked={spec.picked}
              onPicked={(picked) => onSpec({ ...spec, picked })}
            />
            {reading.base_url ? null : (
              <FormField
                label={t("customTools.fields.baseUrl")}
                htmlFor={`${id}-base`}
                required
                help={t("customTools.import.baseUrlMissing")}
              >
                <Input
                  id={`${id}-base`}
                  className="font-mono"
                  placeholder="https://"
                  value={group.baseUrl}
                  onChange={(e) => onGroup({ ...group, baseUrl: e.target.value })}
                />
              </FormField>
            )}
            <GroupHeaderRows
              rows={group.headers}
              onChange={(headers) => onGroup({ ...group, headers })}
              help={t(
                reading.auth_header
                  ? "customTools.import.headersHelpSpec"
                  : "customTools.fields.headersHelp",
              )}
              group={group.name}
            />
            <GroupReachField
              value={group.reach}
              onChange={(reach) => onGroup({ ...group, reach })}
              help={t("customTools.import.availableToHelp")}
            />
            {trying ? <TryOperation reading={reading} group={group} picked={spec.picked} /> : null}
          </>
        ) : null}
      </div>
      <DialogFooter className="sm:justify-between">
        {reading ? (
          <Button variant="outline" onClick={() => setTrying((v) => !v)}>
            <Play aria-hidden />
            {t("customTools.import.try")}
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button variant="ghost" onClick={props.onCancel}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!ready || spec.picked.length === 0} onClick={props.onNext}>
            {reading
              ? t("customTools.import.reviewCount", { count: spec.picked.length })
              : t("customTools.import.review")}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
