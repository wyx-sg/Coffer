// src/components/custom-tools/ToolTestSection.tsx — Test, at the bottom of every request form: a sample
// value per argument, one run of the request as the form holds it (nothing is saved), and the result.
// A saved group's request runs with its secret; a group not saved yet runs without one.
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
import { translateApiError } from "@/lib/api/errors";
import type {
  CustomToolEnvironment,
  CustomToolHeaderIn,
  CustomToolIn,
} from "@/lib/api/customTools";
import { testArguments, type ArgRow } from "@/lib/customTools/schemaArgs";
import { useTestCustomTool, useTestUnsavedCustomTool } from "@/lib/hooks/useCustomTools";
import { useSecretChoices } from "@/components/secret/useSecretChoices";
import { ToolTestResult } from "./ToolTestResult";

/** Where the request runs: a saved group by name, or an unsaved group's settings. */
export type TestTarget =
  | { group: string }
  | { unsaved: { name: string; base_url: string; headers: CustomToolHeaderIn[] } };

interface Props {
  target: TestTarget;
  secret: string | null;
  timeoutSeconds: number;
  args: ArgRow[];
  /** The draft as the form holds it now. */
  draft: () => CustomToolIn;
  ready: boolean;
  /** What the form's save button says: "save" (Save) or "add" (Add to …). */
  saveWord: "save" | "add";
  /** A timed-out run offers Change timeout, which opens Edit group (a saved group only). */
  onChangeTimeout?: () => void;
  /** A saved group's environments: the run names one (spec mcp-gateway "Choose a custom
   *  tool's environment on every call"); a picker shows once more than one is on. */
  environments?: readonly CustomToolEnvironment[];
}

export function ToolTestSection(props: Props) {
  const { target, secret, args, draft, ready } = props;
  const { displayOf } = useSecretChoices();
  const { t } = useTranslation();
  const saved = useTestCustomTool("group" in target ? target.group : "");
  const unsaved = useTestUnsavedCustomTool();
  const test = "group" in target ? saved : unsaved;
  const [values, setValues] = useState<Record<string, string>>({});
  const enabled = (props.environments ?? []).filter((e) => e.enabled);
  const [environment, setEnvironment] = useState<string>(enabled[0]?.name ?? "");
  const chosen = enabled.find((e) => e.name === environment) ?? enabled[0];
  const named = args.filter((row) => row.name);
  const groupName = "group" in target ? target.group : target.unsaved.name;

  const run = () => {
    const tool = draft();
    const argValues = testArguments(args, values);
    if ("group" in target)
      return saved.mutate({ tool, args: argValues, environment: chosen?.name ?? null });
    unsaved.mutate({
      base_url: target.unsaved.base_url,
      headers: target.unsaved.headers,
      timeout_seconds: props.timeoutSeconds,
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

  return (
    <section aria-label={t("customTools.test.title")} className="flex flex-col gap-2">
      <div className="flex min-h-control-sm flex-wrap items-center gap-2">
        <span className="text-xs font-label">{t("customTools.test.title")}</span>
        {"group" in target && enabled.length > 1 ? (
          <Select value={chosen?.name ?? ""} onValueChange={setEnvironment}>
            <SelectTrigger
              className="h-control-sm w-auto min-w-[96px] font-mono text-xs"
              aria-label={t("customTools.test.environment")}
            >
              <SelectValue />
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
        {named.map((row, i) => (
          <label
            key={row.name}
            className="inline-flex items-center gap-1 font-mono text-xs text-text-muted"
          >
            {i > 0 ? <span aria-hidden>·</span> : null}
            {row.name} =
            <input
              className="h-control-sm w-24 rounded-sm border border-border-subtle bg-surface-raised px-1.5 font-mono text-xs text-text focus-visible:border-accent focus-visible:outline-none"
              aria-label={t("customTools.test.valueFor", { name: row.name })}
              value={values[row.name] ?? ""}
              onChange={(e) => setValues({ ...values, [row.name]: e.target.value })}
            />
          </label>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          disabled={!ready || test.isPending}
          onClick={run}
        >
          <RotateCw aria-hidden />
          {test.isPending
            ? t("customTools.test.running")
            : test.data
              ? t("customTools.test.runAgain")
              : t("customTools.test.run")}
        </Button>
      </div>
      {test.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, test.error)}
        </p>
      ) : test.data ? (
        <ToolTestResult
          result={test.data}
          method={draft().method ?? "GET"}
          group={groupName}
          secret={"group" in target ? secret : null}
          timeoutSeconds={props.timeoutSeconds}
          onChangeTimeout={"group" in target ? props.onChangeTimeout : undefined}
        />
      ) : (
        <p className="rounded-lg border border-dashed border-border px-3 py-2.5 text-xs text-text-muted">
          {t("customTools.test.notRun")}
        </p>
      )}
      <p className="text-xs text-text-muted">{note}</p>
    </section>
  );
}
