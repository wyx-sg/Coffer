// src/components/custom-tools/ToolArgumentsField.tsx — the tool's arguments: the top-level properties of its
// input schema, one row each (name, type, required, the description agents read).
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { emptyArg, type ArgRow, type ArgType } from "@/lib/customTools/schemaArgs";

const EDITABLE_TYPES: readonly ArgType[] = ["string", "number", "integer", "boolean", "enum"];

interface Props {
  args: ArgRow[];
  onChange: (args: ArgRow[]) => void;
}

export function ToolArgumentsField({ args, onChange }: Props) {
  const { t } = useTranslation();
  const set = (i: number, row: ArgRow) => onChange(args.map((a, j) => (j === i ? row : a)));
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.editor.arguments")}</Label>
      {args.length > 0 ? (
        <div className="rounded-lg border border-border-subtle">
          <div className="grid grid-cols-[1fr_7rem_4rem_1.5fr_2rem] gap-2 border-b border-border-subtle px-2 py-1.5 text-2xs font-semibold text-text-subtle">
            <span>{t("customTools.editor.argName")}</span>
            <span>{t("customTools.editor.argType")}</span>
            <span>{t("customTools.editor.argRequired")}</span>
            <span>{t("customTools.editor.argDescription")}</span>
            <span />
          </div>
          {args.map((row, i) => (
            <div
              key={i}
              className="grid grid-cols-[1fr_7rem_4rem_1.5fr_2rem] items-center gap-2 border-b border-border-subtle px-2 py-1.5 last:border-b-0"
            >
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
                  <SelectTrigger className="font-mono" aria-label={t("customTools.editor.argType")}>
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
              <div className="flex flex-col gap-1">
                <Input
                  value={row.description}
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
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("customTools.editor.removeArgument")}
                onClick={() => onChange(args.filter((_, j) => j !== i))}
              >
                <X aria-hidden />
              </Button>
            </div>
          ))}
        </div>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-fit"
        onClick={() => onChange([...args, emptyArg()])}
      >
        <Plus aria-hidden />
        {t("customTools.editor.addArgument")}
      </Button>
    </div>
  );
}
