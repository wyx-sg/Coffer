// src/components/custom-tools/ToolRequestFields.tsx — the drawer's request: the tool's name, method + path
// (one compound field), the description agents read, the changes-data flag and the body template.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { HTTP_METHODS, type HttpMethod } from "@/lib/api/customTools";
import { FormField } from "./FormField";
import { withMethod, type ToolForm } from "./toolForm";

interface Props {
  form: ToolForm;
  onChange: (form: ToolForm) => void;
  baseUrl: string;
  group: string;
}

export function ToolRequestFields({ form, onChange, baseUrl, group }: Props) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="flex flex-col gap-4">
      <FormField
        label={t("customTools.editor.name")}
        htmlFor={`${id}-name`}
        required
        help={t("customTools.editor.nameHelp", { name: `${group}__${form.name || "…"}` })}
      >
        <Input
          id={`${id}-name`}
          className="font-mono"
          value={form.name}
          onChange={(e) => onChange({ ...form, name: e.target.value.trim() })}
        />
      </FormField>
      <FormField
        label={t("customTools.editor.request")}
        htmlFor={`${id}-path`}
        required
        help={t("customTools.editor.requestHelp", { url: baseUrl })}
      >
        <div className="flex gap-2">
          <Select
            value={form.method}
            onValueChange={(method) => onChange(withMethod(form, method as HttpMethod))}
          >
            <SelectTrigger className="w-28 font-mono" aria-label={t("customTools.editor.method")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HTTP_METHODS.map((method) => (
                <SelectItem key={method} value={method} className="font-mono">
                  {method}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            id={`${id}-path`}
            className="flex-1 font-mono"
            value={form.path}
            onChange={(e) => onChange({ ...form, path: e.target.value })}
          />
        </div>
      </FormField>
      <FormField
        label={t("customTools.editor.description")}
        htmlFor={`${id}-desc`}
        required
        help={t("customTools.editor.descriptionHelp")}
      >
        <Textarea
          id={`${id}-desc`}
          rows={2}
          value={form.description}
          onChange={(e) => onChange({ ...form, description: e.target.value })}
        />
      </FormField>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <label htmlFor={`${id}-changes`} className="text-xs font-label">
            {t("customTools.tools.changesData")}
          </label>
          <p className="text-xs text-text-muted">{t("customTools.editor.changesDataHelp")}</p>
        </div>
        <Switch
          id={`${id}-changes`}
          checked={form.changesData}
          onCheckedChange={(changesData) =>
            onChange({ ...form, changesData, changesDataSet: true })
          }
        />
      </div>
      <FormField
        label={t("customTools.editor.body")}
        htmlFor={`${id}-body`}
        help={t("customTools.editor.bodyHelp")}
      >
        <Textarea
          id={`${id}-body`}
          rows={4}
          className="font-mono text-xs"
          value={form.body}
          disabled={form.method === "GET"}
          onChange={(e) => onChange({ ...form, body: e.target.value })}
        />
      </FormField>
    </div>
  );
}
