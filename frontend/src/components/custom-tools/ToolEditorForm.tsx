// src/components/custom-tools/ToolEditorForm.tsx — one tool's editor (4.2.30–33), shared by the tool drawer and Add
// a request, five tabs at the full width: General (name, description, changes data, what agents see), Request
// (method and path, query parameters, headers, body), Inputs (the arguments agents fill, each with where the
// request uses it), Response (when a call counts as failed, and what the agent gets) and Test, which runs the form
// as it holds it now. Nothing is saved here: the drawer's Save and the dialog's Add do that.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { CustomToolHeaderOut, ResponseRule } from "@/lib/api/customTools";
import { cn } from "@/lib/utils";
import {
  argumentProblems,
  argumentUses,
  splitPath,
  joinPath,
} from "@/lib/customTools/requestParts";
import { ToolArgumentsField } from "./ToolArgumentsField";
import { ToolHeadersField } from "./ToolHeadersField";
import { ToolQueryField } from "./ToolQueryField";
import {
  BodyField,
  ChangesDataField,
  DescriptionField,
  NameField,
  RequestField,
} from "./ToolRequestFields";
import { ToolResponseTab } from "./ToolResponseTab";
import { ToolTestSection, type TestTarget } from "./ToolTestSection";
import { toolOf, type ToolForm } from "./toolForm";

export type EditorTab = "general" | "request" | "arguments" | "response" | "test";

interface Props {
  form: ToolForm;
  onChange: (form: ToolForm) => void;
  group: string;
  /** A saved tool: its name is fixed. */
  nameLocked: boolean;
  /** The base URL the path is added to, and the environment it is when the group has several. */
  baseUrl: string;
  environment: string | null;
  /** The chosen environment's headers, shown read-only above the tool's own. */
  groupHeaders: readonly CustomToolHeaderOut[];
  /** The group's response rules, for the Response tab to show or start from; none before the group exists. */
  groupRules: readonly ResponseRule[];
  /** The environments agents can name in `coffer_environment`. */
  environments: readonly string[];
  test: TestTarget;
  timeoutSeconds?: number;
  saveWord: "save" | "add";
  onChangeTimeout?: () => void;
  /** The tab it opens on: General for a new tool, Request for a saved one. */
  initialTab: EditorTab;
  className?: string;
}

export function ToolEditorForm(props: Props) {
  const { form, onChange, group } = props;
  const { t } = useTranslation();
  const [tab, setTab] = useState<EditorTab>(props.initialTab);
  // The input a query chip on the Request tab opened.
  const [focusInput, setFocusInput] = useState<string | null>(null);
  const showInput = (name: string) => {
    setFocusInput(name);
    setTab("arguments");
  };
  const uses = argumentUses({
    path: form.path,
    headers: form.headers,
    body: form.body,
    sendsBody: form.method !== "GET",
  });
  const problems = argumentProblems(
    form.args.map((a) => a.name),
    uses,
  );
  const problemCount = problems.unused.length + problems.missing.length;
  const addToQuery = (name: string) => {
    const { base, query } = splitPath(form.path);
    onChange({ ...form, path: joinPath(base, [...query, { key: name, value: `{${name}}` }]) });
  };

  return (
    <Tabs
      value={tab}
      onValueChange={(v) => {
        setTab(v as EditorTab);
        if (v !== "arguments") setFocusInput(null);
      }}
      className={cn("flex min-h-0 flex-1 flex-col", props.className)}
    >
      <TabsList className="shrink-0 px-5">
        <TabsTrigger value="general">{t("customTools.editor.tabs.general")}</TabsTrigger>
        <TabsTrigger value="request">{t("customTools.editor.tabs.request")}</TabsTrigger>
        <TabsTrigger value="arguments">
          {t("customTools.editor.tabs.arguments")}
          {problemCount > 0 ? (
            <Badge variant="warning">{problemCount}</Badge>
          ) : form.args.length > 0 ? (
            <Badge variant="secondary">{form.args.length}</Badge>
          ) : null}
        </TabsTrigger>
        <TabsTrigger value="response">{t("customTools.editor.tabs.response")}</TabsTrigger>
        <TabsTrigger value="test">{t("customTools.editor.tabs.test")}</TabsTrigger>
      </TabsList>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        <TabsContent value="general" className="flex flex-col gap-5">
          <NameField form={form} onChange={onChange} group={group} locked={props.nameLocked} />
          <DescriptionField form={form} onChange={onChange} />
          <ChangesDataField form={form} onChange={onChange} />
          <AgentPreview form={form} group={group} environments={props.environments} />
        </TabsContent>
        <TabsContent value="request" className="flex flex-col gap-5">
          <RequestField
            form={form}
            onChange={onChange}
            baseUrl={props.baseUrl}
            environment={props.environment}
            adding={props.saveWord === "add"}
          />
          <ToolQueryField
            path={form.path}
            onChange={(path) => onChange({ ...form, path })}
            onShowInput={showInput}
          />
          <ToolHeadersField
            groupHeaders={props.groupHeaders}
            headers={form.headers}
            onChange={(headers) => onChange({ ...form, headers })}
            environment={props.environment}
            forThisRequest
          />
          <BodyField form={form} onChange={onChange} />
        </TabsContent>
        <TabsContent value="arguments">
          <ToolArgumentsField
            args={form.args}
            onChange={(args) => onChange({ ...form, args })}
            uses={uses}
            onAddToQuery={addToQuery}
            focus={focusInput}
          />
        </TabsContent>
        <TabsContent value="response" className="flex flex-col gap-4">
          <ToolResponseTab form={form} onChange={onChange} groupRules={props.groupRules} />
        </TabsContent>
        {/* Kept mounted: the sample values and the last result survive a trip to another tab. */}
        <TabsContent value="test" forceMount>
          <ToolTestSection
            target={props.test}
            timeoutSeconds={props.timeoutSeconds}
            args={form.args}
            draft={() => toolOf(form)}
            ready={form.path.trim() !== "" && form.name !== ""}
            saveWord={props.saveWord}
            onChangeTimeout={props.onChangeTimeout}
          />
        </TabsContent>
      </div>
    </Tabs>
  );
}

/** What an agent is shown: the full name with its arguments, the description and the hints. */
function AgentPreview({
  form,
  group,
  environments,
}: {
  form: ToolForm;
  group: string;
  environments: readonly string[];
}) {
  const { t } = useTranslation();
  const args = form.args
    .filter((a) => a.name)
    .map((a) => (a.required ? `${a.name}*` : a.name))
    .join(", ");
  return (
    <section
      aria-label={t("customTools.editor.agentPreview")}
      className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-3"
    >
      <span className="text-xs font-label text-text-muted">
        {t("customTools.editor.agentPreview")}
      </span>
      <span className="break-all font-mono text-xs">
        {group}__{form.name || "…"}({args})
      </span>
      {form.description.trim() ? (
        <span className="text-xs text-text-muted">{form.description.trim()}</span>
      ) : null}
      <span className="flex flex-wrap gap-1.5">
        <Badge variant="secondary">
          {t(
            form.changesData ? "customTools.editor.hintChanges" : "customTools.editor.hintReadOnly",
          )}
        </Badge>
        {environments.length > 0 ? (
          <Badge variant="secondary" className="font-mono">
            coffer_environment: {environments.join(" | ")}
          </Badge>
        ) : null}
      </span>
    </section>
  );
}
