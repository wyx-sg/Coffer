// src/components/custom-tools/ToolTestSection.tsx — Try it, the right-hand column of every tool editor: a sample
// value per argument, one run of the request as the form holds it (nothing is saved), and the result — beside it,
// on its own tab, the request the run sends.
// A saved group's request runs in the environment the form has chosen — the same one its preview, secret
// and timeout come from; the picker only changes that choice, never the group. A group not saved yet runs
// without a secret.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup, CustomToolHeaderIn, CustomToolIn } from "@/lib/api/customTools";
import {
  effectiveTimeout,
  enabledEnvironments,
  environmentSecret,
} from "@/lib/customTools/environmentContext";
import { testArguments, type ArgRow } from "@/lib/customTools/schemaArgs";
import { useTestCustomTool, useTestUnsavedCustomTool } from "@/lib/hooks/useCustomTools";
import { useSecretChoices } from "@/components/secret/useSecretChoices";
import { RequestPreview } from "./RequestPreview";
import { ToolTestResult } from "./ToolTestResult";
import type { ToolEnvironment } from "./useToolEnvironment";

/** Where the request runs: a saved group in the form's chosen environment, or an unsaved group's settings. */
export type TestTarget =
  | { saved: CustomToolGroup; environment: ToolEnvironment }
  | { unsaved: { name: string; base_url: string; headers: CustomToolHeaderIn[] } };

interface Props {
  target: TestTarget;
  /** An unsaved group's timeout; a saved group's comes from the chosen environment. */
  timeoutSeconds?: number;
  args: ArgRow[];
  /** The draft as the form holds it now. */
  draft: () => CustomToolIn;
  ready: boolean;
  /** What the form's save button says: "save" (Save) or "add" (Add to …). */
  saveWord: "save" | "add";
  /** A run that timed out on the group's timeout offers Change timeout, which opens Edit group. */
  onChangeTimeout?: () => void;
}

export function ToolTestSection(props: Props) {
  const { target, args, draft, ready } = props;
  const { displayOf } = useSecretChoices();
  const { t } = useTranslation();
  const group = "saved" in target ? target.saved : null;
  const choice = "saved" in target ? target.environment : null;
  const saved = useTestCustomTool(group?.name ?? "");
  const unsaved = useTestUnsavedCustomTool();
  const test = group ? saved : unsaved;
  const [values, setValues] = useState<Record<string, string>>({});
  // Try it shows the request a run would send (the preview) until a run, then its result; one at a time.
  const [view, setView] = useState<"result" | "request">("request");
  const enabled = group ? enabledEnvironments(group) : [];
  const env = choice?.env ?? null;
  const named = args.filter((row) => row.name);
  const groupName = group ? group.name : "unsaved" in target ? target.unsaved.name : "";
  const secret = env ? environmentSecret(env) : null;
  const timeout =
    group && env
      ? effectiveTimeout(group, env)
      : { seconds: group?.timeout_seconds ?? props.timeoutSeconds ?? 30, source: "group" as const };
  const blocked = choice !== null && choice.choice.state !== "ok";
  const showPicker = group !== null && (enabled.length > 1 || (blocked && enabled.length > 0));

  const pick = (name: string) => {
    choice?.setName(name);
    saved.reset();
  };
  const run = () => {
    const tool = draft();
    const argValues = testArguments(args, values);
    setView("result");
    if (group) {
      if (env) saved.mutate({ tool, args: argValues, environment: env.name });
      return;
    }
    if ("unsaved" in target)
      unsaved.mutate({
        base_url: target.unsaved.base_url,
        headers: target.unsaved.headers,
        timeout_seconds: timeout.seconds,
        tool,
        arguments: argValues,
      });
  };
  const note =
    "unsaved" in target
      ? t(`customTools.test.noteUnsaved.${props.saveWord}`)
      : secret
        ? t(`customTools.test.noteSecret.${props.saveWord}`, { secret: displayOf(secret) })
        : t(`customTools.test.note.${props.saveWord}`);
  const state = choice?.choice;
  const unavailable =
    state?.state === "none"
      ? t("customTools.test.envNone")
      : state?.state === "disabled" || state?.state === "deleted"
        ? t(`customTools.test.env.${state.state}`, { environment: state.name })
        : null;

  const preview =
    group && env ? (
      <RequestPreview group={group} environment={env} method={draft().method ?? "GET"} tool={draft()} />
    ) : null;
  const result = test.error ? (
    <p role="alert" className="text-xs text-danger">
      {translateApiError(t, test.error)}
    </p>
  ) : test.data ? (
    <ToolTestResult
      result={test.data}
      method={draft().method ?? "GET"}
      group={groupName}
      secret={group ? secret : null}
      timeoutSeconds={timeout.seconds}
      timeoutEnvironment={timeout.source === "environment" ? (env?.name ?? null) : null}
      onChangeTimeout={group && timeout.source === "group" ? props.onChangeTimeout : undefined}
    />
  ) : (
    <p className="rounded-lg border border-dashed border-border px-3 py-2.5 text-xs text-text-muted">
      {t("customTools.test.notRun")}
    </p>
  );

  return (
    <section aria-label={t("customTools.test.title")} className="flex flex-col gap-3">
      <div className="flex min-h-control-sm items-center gap-2">
        <span className="text-xs font-label">{t("customTools.test.title")}</span>
        {showPicker ? (
          <Select value={env?.name ?? ""} onValueChange={pick}>
            <SelectTrigger
              className="ml-auto h-control-sm w-auto min-w-[120px] font-mono text-xs"
              aria-label={t("customTools.test.environment")}
            >
              <SelectValue placeholder={t("customTools.test.pickEnvironment")} />
            </SelectTrigger>
            <SelectContent>
              {enabled.map((e) => (
                <SelectItem key={e.name} value={e.name} className="font-mono text-xs">
                  {e.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
      </div>
      {named.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {named.map((row) => (
            <label
              key={row.name}
              className="grid grid-cols-[8rem_minmax(0,1fr)] items-center gap-2 font-mono text-xs"
            >
              <span className="truncate">
                {row.name}
                {row.required ? <span className="text-danger">*</span> : null}{" "}
                <span className="text-2xs text-text-muted">
                  {row.type === "other" ? row.rawType : row.type}
                </span>
              </span>
              <input
                className="h-control-sm min-w-0 rounded-sm border border-border-subtle bg-surface-raised px-2 font-mono text-xs text-text focus-visible:border-accent focus-visible:outline-none"
                aria-label={t("customTools.test.valueFor", { name: row.name })}
                value={values[row.name] ?? ""}
                onChange={(e) => setValues({ ...values, [row.name]: e.target.value })}
              />
            </label>
          ))}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={!ready || blocked || test.isPending} onClick={run}>
          <RotateCw aria-hidden />
          {test.isPending
            ? t("customTools.test.running")
            : test.data
              ? t("customTools.test.runAgain")
              : t("customTools.test.run")}
        </Button>
      </div>
      {unavailable ? (
        <p role="alert" className="text-xs text-warning">
          {unavailable}
        </p>
      ) : null}
      {preview ? (
        <Tabs value={view} onValueChange={(v) => setView(v as "result" | "request")}>
          <TabsList className="h-8">
            <TabsTrigger value="result">{t("customTools.test.resultTab")}</TabsTrigger>
            <TabsTrigger value="request">{t("customTools.test.requestTab")}</TabsTrigger>
          </TabsList>
          <TabsContent value="result" className="mt-3">
            {result}
          </TabsContent>
          <TabsContent value="request" className="mt-3">
            {preview}
          </TabsContent>
        </Tabs>
      ) : (
        result
      )}
      <p className="text-xs text-text-muted">{note}</p>
    </section>
  );
}
