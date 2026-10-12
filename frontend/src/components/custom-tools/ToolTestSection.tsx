// src/components/custom-tools/ToolTestSection.tsx — Test, the editor's last tab (and Import's Try an operation): the
// full width, top to bottom — where it runs and Run; a sample value per input; the request a run sends with those
// values (RequestPreview); the response once it has run (ToolTestResult). One run sends the request as the form
// holds it now; nothing is saved.
// A saved group's request runs in the environment the tab has chosen — the same one the Request tab's help and
// headers read; the picker only changes that choice, never the group. A group not saved yet runs without a secret.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import type {
  CustomToolGroup,
  CustomToolHeaderIn,
  CustomToolHeaderOut,
  CustomToolIn,
} from "@/lib/api/customTools";
import {
  effectiveTimeout,
  enabledEnvironments,
  environmentSecret,
  requestPreview,
} from "@/lib/customTools/environmentContext";
import { testArguments, type ArgRow } from "@/lib/customTools/schemaArgs";
import { sentRequest } from "@/lib/customTools/sentRequest";
import { useTestCustomTool, useTestUnsavedCustomTool } from "@/lib/hooks/useCustomTools";
import { useSecretChoices } from "@/components/secret/useSecretChoices";
import { RequestPreview } from "./RequestPreview";
import { TestValues } from "./TestValues";
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

/** An unsaved group's header rows as the preview reads a saved environment's. */
function headersOut(headers: readonly CustomToolHeaderIn[]): CustomToolHeaderOut[] {
  return headers.map((h) => ({
    name: h.name,
    value: h.value ?? null,
    secret: h.secret ?? null,
    scheme: h.scheme ?? null,
    secret_state: "none",
  }));
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
  const responseRef = useRef<HTMLElement | null>(null);
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
  const tool = draft();
  const method = tool.method ?? "GET";
  const argValues = testArguments(args, values);

  const pick = (name: string) => {
    choice?.setName(name);
    saved.reset();
  };
  // A run's answer is below the request: bring it into view when it arrives.
  useEffect(() => {
    if (test.data || test.error)
      responseRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [test.data, test.error]);
  const run = () => {
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

  // The environment the request is built in: the chosen one, or an unsaved group's settings.
  const previewEnv = env
    ? env
    : "unsaved" in target && target.unsaved.base_url
      ? {
          base_url: target.unsaved.base_url,
          headers: headersOut(target.unsaved.headers),
          variables: {},
        }
      : null;
  const variables = previewEnv?.variables ?? {};
  const lines = previewEnv ? requestPreview(previewEnv, tool) : null;
  const preview = lines ? (
    <RequestPreview
      method={method}
      sent={sentRequest(lines, { ...tool, method }, argValues, variables)}
      environment={group && env ? env.name : null}
      variables={variables}
      missingVariables={lines.missingVariables}
      timeoutLine={
        group && env
          ? t(`customTools.preview.timeout.${timeout.source}`, {
              seconds: timeout.seconds,
              environment: env.name,
            })
          : t("customTools.preview.timeout.group", { seconds: timeout.seconds })
      }
    />
  ) : null;
  const result = test.error ? (
    <p role="alert" className="text-xs text-danger">
      {translateApiError(t, test.error)}
    </p>
  ) : test.data ? (
    <ToolTestResult
      result={test.data}
      method={method}
      group={groupName}
      secret={group ? secret : null}
      timeoutSeconds={timeout.seconds}
      timeoutEnvironment={timeout.source === "environment" ? (env?.name ?? null) : null}
      onChangeTimeout={group && timeout.source === "group" ? props.onChangeTimeout : undefined}
    />
  ) : (
    <p className="rounded-lg border border-dashed border-border px-3 py-2.5 text-xs text-text-muted">
      {t(test.isPending ? "customTools.test.running" : "customTools.test.notRun")}
    </p>
  );

  return (
    <section aria-label={t("customTools.test.title")} className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <div className="flex min-h-control-md flex-wrap items-center gap-2">
          <h3 className="text-sm font-label">{t("customTools.test.valuesTitle")}</h3>
          <span className="ml-auto inline-flex items-center gap-2">
            {showPicker ? (
              <Select value={env?.name ?? ""} onValueChange={pick}>
                <SelectTrigger
                  className="h-control-md w-auto min-w-[120px] font-mono text-xs"
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
            <Button disabled={!ready || blocked || test.isPending} onClick={run}>
              <Play aria-hidden />
              {test.isPending
                ? t("customTools.test.running")
                : test.data
                  ? t("customTools.test.runAgain")
                  : t("customTools.test.run")}
            </Button>
          </span>
        </div>
        {unavailable ? (
          <p role="alert" className="text-xs text-warning">
            {unavailable}
          </p>
        ) : null}
        <TestValues inputs={named} values={values} onChange={setValues} />
        <p className="text-xs text-text-muted">{note}</p>
      </div>
      {preview}
      <section
        ref={responseRef}
        aria-label={t("customTools.test.responseTitle")}
        className="flex scroll-mt-4 flex-col gap-3"
      >
        <h3 className="text-sm font-label">{t("customTools.test.responseTitle")}</h3>
        {result}
      </section>
    </section>
  );
}
