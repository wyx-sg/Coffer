// src/components/custom-tools/ToolRequestFields.tsx — the fields of one request, which the Add a request
// step and the tool drawer lay out on the editor's tabs (ToolEditorForm): the tool's name, method + path (one compound
// field), the description agents read, the changes-data flag and the body template (a JSON editor
// that marks its `{holes}` and lays it out on Format). The base URL the path is added to is the form's chosen
// environment's.
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { WrapText } from "lucide-react";

import { CodeEditor } from "@/components/preview/CodeEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { bodyTemplateProblem, formatBodyTemplate } from "@/lib/customTools/bodyTemplate";
import { FormField } from "./FormField";
import { holeMarks } from "./holeMarks";
import { withMethod, type ToolForm } from "./toolForm";

interface FieldProps {
  form: ToolForm;
  onChange: (form: ToolForm) => void;
}

/** The `{holes}` of a path, in order. */
function holesOf(path: string): string[] {
  return [...path.matchAll(/\{([A-Za-z_][A-Za-z0-9_.-]*)\}/g)].map((m) => m[1]);
}

/** `locked`: a saved tool, whose name is fixed — it is part of the name agents call. */
export function NameField({
  form,
  onChange,
  group,
  locked = false,
}: FieldProps & { group: string; locked?: boolean }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <FormField
      label={t("customTools.editor.name")}
      htmlFor={id}
      required={!locked}
      help={
        locked
          ? t("customTools.editor.nameFixed")
          : t("customTools.editor.nameHelp", { name: `${group}__${form.name || "…"}` })
      }
    >
      <Input
        id={id}
        className="font-mono"
        value={form.name}
        disabled={locked}
        readOnly={locked}
        onChange={(e) => onChange({ ...form, name: e.target.value.trim() })}
      />
    </FormField>
  );
}

/** `adding`: the help names the arguments the path's holes come from. */
/** `environment`: the group has several, and `baseUrl` is this one's — the help names it. An empty
 *  `baseUrl` (no environment chosen) says where the path goes instead of naming a URL. */
export function RequestField({
  form,
  onChange,
  baseUrl,
  environment = null,
  adding = false,
}: FieldProps & { baseUrl: string; environment?: string | null; adding?: boolean }) {
  const { t } = useTranslation();
  const id = useId();
  const holes = holesOf(form.path).map((h) => `{${h}}`);
  const help = !baseUrl
    ? t("customTools.editor.requestHelpNoEnv")
    : environment
      ? t("customTools.editor.requestHelpEnv", { url: baseUrl, environment })
      : adding && holes.length > 0
        ? t("customTools.editor.requestHelpArgs", {
            url: baseUrl,
            holes: holes.join(t("customTools.editor.and")),
          })
        : adding
          ? t("customTools.editor.requestHelpAdd", { url: baseUrl })
          : t("customTools.editor.requestHelp", { url: baseUrl });
  return (
    <FormField label={t("customTools.editor.request")} htmlFor={id} required help={help}>
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
          id={id}
          className="flex-1 font-mono"
          value={form.path}
          onChange={(e) => onChange({ ...form, path: e.target.value })}
        />
      </div>
    </FormField>
  );
}

export function DescriptionField({ form, onChange }: FieldProps) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <FormField
      label={t("customTools.editor.description")}
      htmlFor={id}
      required
      help={t("customTools.editor.descriptionHelp")}
    >
      <Textarea
        id={id}
        autoGrow
        className="min-h-[96px]"
        value={form.description}
        onChange={(e) => onChange({ ...form, description: e.target.value })}
      />
    </FormField>
  );
}

/** `short`: the Add a request wording, without the approval-prompt clause. */
export function ChangesDataField({
  form,
  onChange,
  short = false,
}: FieldProps & { short?: boolean }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <Switch
        id={id}
        className="mt-0.5"
        checked={form.changesData}
        onCheckedChange={(changesData) => onChange({ ...form, changesData, changesDataSet: true })}
      />
      <div className="space-y-0.5">
        <label htmlFor={id} className="text-xs font-label">
          {t("customTools.tools.changesData")}
        </label>
        <p className="text-xs text-text-muted">
          {t(
            short
              ? "customTools.editor.changesDataHelpShort"
              : "customTools.editor.changesDataHelp",
          )}
        </p>
      </div>
    </div>
  );
}

export function BodyField({ form, onChange }: FieldProps) {
  const { t } = useTranslation();
  const id = useId();
  // A GET sends no body: the field says so instead of showing a box that takes nothing.
  if (form.method === "GET")
    return (
      <FormField label={t("customTools.editor.body")}>
        <p className="text-xs text-text-muted">{t("customTools.editor.bodyGet")}</p>
      </FormField>
    );
  const problem = bodyTemplateProblem(form.body);
  const formatted = formatBodyTemplate(form.body);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex min-h-control-sm items-center gap-2">
        <Label htmlFor={id}>{t("customTools.editor.body")}</Label>
        <span className="text-xs text-text-muted">JSON</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto"
          disabled={formatted === null || formatted === form.body}
          onClick={() => formatted !== null && onChange({ ...form, body: formatted })}
        >
          <WrapText aria-hidden />
          {t("customTools.editor.format")}
        </Button>
      </div>
      <CodeEditor
        id={id}
        language="json"
        value={form.body}
        onChange={(body) => onChange({ ...form, body })}
        invalid={problem !== null}
        placeholder={t("customTools.editor.bodyHelp")}
        ariaLabel={t("customTools.editor.body")}
        extensions={holeMarks}
      />
      {problem ? (
        <p role="alert" className="text-xs text-danger">
          {t("customTools.editor.bodyInvalid", problem)}
        </p>
      ) : (
        <p className="text-xs text-text-muted">{t("customTools.editor.bodyHoles")}</p>
      )}
    </div>
  );
}
