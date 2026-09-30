// src/components/custom-tools/AddRequestStep.tsx — Add a request: one hand-made request into the group
// picked in the first step, tested at the bottom of the form. Into an existing group it uses that
// group's base URL and secret; into a new one it saves the group and its first tool together, on Add.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { FormField } from "./FormField";
import { ToolArgumentsField } from "./ToolArgumentsField";
import { ToolHeadersField } from "./ToolHeadersField";
import {
  BodyField,
  ChangesDataField,
  DescriptionField,
  NameField,
  RequestField,
} from "./ToolRequestFields";
import { ToolTestSection, type TestTarget } from "./ToolTestSection";
import type { GroupDraft } from "./addFlow";
import { WaySummary } from "./WaySummary";
import { formOf, formReady, groupAuthOf, toolOf, type ToolForm } from "./toolForm";

/** The group the request goes into: saved, or the draft the New group step made. */
export type RequestGroup = { saved: CustomToolGroup } | { draft: GroupDraft };

interface Props {
  group: RequestGroup;
  pending: boolean;
  error: unknown;
  onChangeWay: () => void;
  onCancel: () => void;
  onAdd: (form: ToolForm) => void;
}

export function AddRequestStep({ group, pending, error, onChangeWay, onCancel, onAdd }: Props) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ToolForm>(() => formOf(null));
  const saved = "saved" in group ? group.saved : null;
  const name = saved ? saved.name : "draft" in group ? group.draft.name : "";
  const baseUrl = saved ? saved.base_url : "draft" in group ? group.draft.baseUrl.trim() : "";
  const draftAuth = "draft" in group ? group.draft.auth : null;
  const auth = saved
    ? groupAuthOf(saved)
    : draftAuth?.secret
      ? { header: draftAuth.header, prefix: draftAuth.prefix, secret: draftAuth.secret }
      : null;
  const target: TestTarget = saved
    ? { group: saved.name }
    : { unsaved: { name, base_url: baseUrl, headers: {} } };

  return (
    <>
      <div className="flex flex-col gap-5">
        <WaySummary way="hand" sub={t("customTools.add.handSummary")} onChange={onChangeWay} />
        <FormField
          label={t("customTools.fields.group")}
          required
          help={t("customTools.add.groupPicked")}
        >
          <div
            aria-disabled
            className="flex h-control-md items-center rounded-md border border-border bg-surface-sunken px-2.5 font-mono text-sm text-text-muted"
          >
            {name}
          </div>
        </FormField>
        <NameField form={form} onChange={setForm} group={name} />
        <DescriptionField form={form} onChange={setForm} />
        <RequestField form={form} onChange={setForm} baseUrl={baseUrl} adding />
        <ChangesDataField form={form} onChange={setForm} short />
        <ToolHeadersField
          auth={auth}
          headers={form.headers}
          onChange={(headers) => setForm({ ...form, headers })}
        />
        <BodyField form={form} onChange={setForm} />
        <ToolArgumentsField args={form.args} onChange={(args) => setForm({ ...form, args })} />
        <ToolTestSection
          target={target}
          secret={auth?.secret ?? null}
          timeoutSeconds={saved?.timeout_seconds ?? 30}
          args={form.args}
          draft={() => toolOf(form)}
          ready={form.path.trim() !== "" && form.name !== ""}
          saveWord="add"
        />
        {error ? (
          <div role="alert" className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
            <span>{translateApiError(t, error)}</span>
          </div>
        ) : null}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!formReady(form) || pending} onClick={() => onAdd(form)}>
          {t("customTools.add.addTo", { group: name })}
        </Button>
      </DialogFooter>
    </>
  );
}
