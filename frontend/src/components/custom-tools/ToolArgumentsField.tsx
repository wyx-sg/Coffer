// src/components/custom-tools/ToolArgumentsField.tsx — the tool's arguments: the top-level properties of its input
// schema, one row each (name, type, required, where the request uses it, and the description agents read under
// it). An argument no hole names is sent nowhere, and a hole no argument names can never be filled: both are listed
// under the rows with their fix (Add as query parameter, Remove argument; Add argument).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { argumentProblems, type ArgumentUse } from "@/lib/customTools/requestParts";
import { emptyArg, type ArgRow, type ArgType } from "@/lib/customTools/schemaArgs";

const EDITABLE_TYPES: readonly ArgType[] = ["string", "number", "integer", "boolean", "enum"];
const COLS = "grid-cols-[minmax(0,1fr)_7rem_4.5rem_minmax(0,1fr)_2rem]";

interface Props {
  args: ArgRow[];
  onChange: (args: ArgRow[]) => void;
  /** Where the request uses each argument (requestParts.argumentUses). */
  uses: Map<string, ArgumentUse[]>;
  /** Add as query parameter: `<name>={<name>}` on the path. */
  onAddToQuery: (name: string) => void;
}

function labelOfUse(use: ArgumentUse): string {
  if (use.where === "query") return `?${use.key}=`;
  if (use.where === "header") return use.key;
  return use.where;
}

export function ToolArgumentsField({ args, onChange, uses, onAddToQuery }: Props) {
  const { t } = useTranslation();
  const set = (i: number, row: ArgRow) => onChange(args.map((a, j) => (j === i ? row : a)));
  const { unused, missing } = argumentProblems(
    args.map((a) => a.name),
    uses,
  );
  return (
    <div className="flex flex-col gap-3">
      {args.length > 0 ? (
        <div className="flex flex-col">
          <div className={`grid ${COLS} gap-2 pb-1.5 text-2xs font-semibold text-text-muted`}>
            <span>{t("customTools.editor.argName")}</span>
            <span>{t("customTools.editor.argType")}</span>
            <span>{t("customTools.editor.argRequired")}</span>
            <span>{t("customTools.editor.argUsedIn")}</span>
            <span />
          </div>
          {args.map((row, i) => {
            const used = uses.get(row.name) ?? [];
            return (
              <div
                key={i}
                className="flex flex-col gap-1.5 border-b border-border-subtle py-2.5"
                data-testid={`argument-${row.name}`}
              >
                <div className={`grid ${COLS} items-center gap-2`}>
                  <Input
                    className="font-mono"
                    value={row.name}
                    aria-label={t("customTools.editor.argName")}
                    onChange={(e) => set(i, { ...row, name: e.target.value.trim() })}
                  />
                  {row.type === "other" ? (
                    // An object or array argument keeps its own schema; only its
                    // description and required flag are edited here.
                    <span className="px-1 font-mono text-xs text-text-muted">{row.rawType}</span>
                  ) : (
                    <Select
                      value={row.type}
                      onValueChange={(type) => set(i, { ...row, type: type as ArgType })}
                    >
                      <SelectTrigger
                        className="font-mono"
                        aria-label={t("customTools.editor.argType")}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {EDITABLE_TYPES.map((type) => (
                          <SelectItem key={type} value={type} className="font-mono">
                            {type}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  <Checkbox
                    className="justify-self-center"
                    checked={row.required}
                    aria-label={t("customTools.editor.argRequiredFor", { name: row.name })}
                    onChange={(e) => set(i, { ...row, required: e.target.checked })}
                  />
                  <span className="flex min-w-0 flex-wrap gap-1">
                    {row.name === "" ? null : used.length > 0 ? (
                      used.map((use, k) => (
                        <Badge key={k} className="font-mono">
                          {labelOfUse(use)}
                        </Badge>
                      ))
                    ) : (
                      <Badge variant="warning">{t("customTools.editor.argUnused")}</Badge>
                    )}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("customTools.editor.removeArgument")}
                    onClick={() => onChange(args.filter((_, j) => j !== i))}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </div>
                <Input
                  value={row.description}
                  placeholder={t("customTools.editor.argDescription")}
                  aria-label={t("customTools.editor.argDescription")}
                  onChange={(e) => set(i, { ...row, description: e.target.value })}
                />
                {row.type === "enum" ? (
                  <Input
                    className="font-mono"
                    value={row.enumValues}
                    placeholder={t("customTools.editor.enumValues")}
                    aria-label={t("customTools.editor.enumValues")}
                    onChange={(e) => set(i, { ...row, enumValues: e.target.value })}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-text-muted">{t("customTools.editor.noArguments")}</p>
      )}
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto w-fit px-0 py-0.5"
        onClick={() => onChange([...args, emptyArg()])}
      >
        <Plus aria-hidden />
        {t("customTools.editor.addArgument")}
      </Button>
      {unused.map((name) => (
        <Problem key={`u-${name}`} text={t("customTools.editor.unusedArgument", { name })}>
          <Button type="button" variant="outline" size="sm" onClick={() => onAddToQuery(name)}>
            {t("customTools.editor.addToQuery")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange(args.filter((a) => a.name !== name))}
          >
            {t("customTools.editor.removeArgument")}
          </Button>
        </Problem>
      ))}
      {missing.map((name) => (
        <Problem key={`m-${name}`} text={t("customTools.editor.missingArgument", { name })}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onChange([...args, { ...emptyArg(), name, required: true }])}
          >
            {t("customTools.editor.addArgumentNamed", { name })}
          </Button>
        </Problem>
      ))}
      <p className="text-xs text-text-muted">{t("customTools.editor.argumentsHelp")}</p>
    </div>
  );
}

function Problem({ text, children }: { text: string; children: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2.5"
    >
      <AlertCircle className="mt-0.5 size-[15px] shrink-0 text-warning" aria-hidden />
      <div className="flex flex-col gap-2">
        <span className="text-sm text-text">{text}</span>
        <span className="flex gap-2">{children}</span>
      </div>
    </div>
  );
}
