// src/components/custom-tools/AddRequestStep.tsx — Add a request: one hand-made request into the group
// picked in the first step, tested at the bottom of the form. Into an existing group it uses that
// group's base URL and secret; into a new one it saves the group and its first tool together, on Add.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup, CustomToolHeaderOut } from "@/lib/api/customTools";
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
import { formOf, formReady, toolOf, type ToolForm } from "./toolForm";
import { headersIn } from "./headerRows";

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
  const target: TestTarget = saved
    ? { group: saved.name }
    : {
        unsaved: {
          name,
          base_url: baseUrl,
          headers: "draft" in group ? headersIn(group.draft.headers) : [],
        },
      };
  const groupHeaders: CustomToolHeaderOut[] = saved
    ? saved.headers
    : "draft" in group
      ? headersIn(group.draft.headers).map((h) => ({
          name: h.name,
          value: h.value ?? null,
          secret: h.secret ?? null,
          secret_state: "none",
        }))
      : [];
  const secret = saved?.headers.find((h) => h.secret)?.secret ?? null;

  return (
    <>
      <div className="flex flex-col gap-5">
        <WaySummary
          way="hand"
          into={name}
          sub={t("customTools.add.handSummary")}
          onChange={onChangeWay}
        />
        <NameField form={form} onChange={setForm} group={name} />
        <DescriptionField form={form} onChange={setForm} />
        <RequestField form={form} onChange={setForm} baseUrl={baseUrl} adding />
        <ChangesDataField form={form} onChange={setForm} short />
        <ToolHeadersField
          groupHeaders={groupHeaders}
          headers={form.headers}
          onChange={(headers) => setForm({ ...form, headers })}
        />
        <BodyField form={form} onChange={setForm} />
        <ToolArgumentsField args={form.args} onChange={(args) => setForm({ ...form, args })} />
        <ToolTestSection
          target={target}
          secret={secret}
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
        <Button variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!formReady(form) || pending} onClick={() => onAdd(form)}>
          {error ? t("common.retry") : t("customTools.add.addTo", { group: name })}
        </Button>
      </DialogFooter>
    </>
  );
}
