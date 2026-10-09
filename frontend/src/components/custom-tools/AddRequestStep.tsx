// src/components/custom-tools/AddRequestStep.tsx — Add a request: one hand-made request into the group
// picked in the first step, tested at the bottom of the form. Into an existing group it previews and tests in
// one of that group's environments (its base URL, headers, secret and timeout); into a new one it saves the
// group and its first tool together, on Add.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup, CustomToolHeaderOut } from "@/lib/api/customTools";
import { ToolEditorForm } from "./ToolEditorForm";
import type { TestTarget } from "./ToolTestSection";
import type { GroupDraft } from "./addFlow";
import { WaySummary } from "./WaySummary";
import { formOf, formReady, type ToolForm } from "./toolForm";
import { headersIn } from "./headerRows";
import { useToolEnvironment } from "./useToolEnvironment";

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
  const environment = useToolEnvironment(saved);
  const shown = environment.shown;
  const baseUrl = saved
    ? (shown?.base_url ?? "")
    : "draft" in group
      ? group.draft.baseUrl.trim()
      : "";
  const several = (saved?.environments?.length ?? 0) > 1;
  const target: TestTarget = saved
    ? { saved, environment }
    : {
        unsaved: {
          name,
          base_url: baseUrl,
          headers: "draft" in group ? headersIn(group.draft.headers) : [],
        },
      };
  const groupHeaders: CustomToolHeaderOut[] = saved
    ? (shown?.headers ?? [])
    : "draft" in group
      ? headersIn(group.draft.headers).map((h) => ({
          name: h.name,
          value: h.value ?? null,
          secret: h.secret ?? null,
          scheme: h.scheme ?? null,
          secret_state: "none",
        }))
      : [];

  return (
    <>
      <div className="flex flex-col gap-5">
        <WaySummary
          way="hand"
          into={name}
          sub={t("customTools.add.handSummary")}
          onChange={onChangeWay}
        />
        <ToolEditorForm
          form={form}
          onChange={setForm}
          group={name}
          nameLocked={false}
          baseUrl={baseUrl}
          environment={several ? (shown?.name ?? null) : null}
          groupHeaders={groupHeaders}
          groupRules={saved?.response?.rules ?? []}
          environments={
            saved ? (saved.environments ?? []).filter((e) => e.enabled).map((e) => e.name) : []
          }
          test={target}
          timeoutSeconds={30}
          saveWord="add"
          initialTab="general"
          className="-mx-5 h-[min(620px,64vh)] flex-none border-y border-border-subtle pt-1"
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
