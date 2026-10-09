// src/components/custom-tools/ResponseRulesField.tsx — a list of response rules, one row each: what to read (the HTTP
// status, a response header or a JSON field), its name, the values that mean success, what a missing value means and
// where the API puts its own error message. Shared by Edit group (the group's rules) and the tool editor's Response
// tab (one tool's own). The text of "Success values" is kept here so a typed comma survives; the rules go up on every
// edit. The server stays the authority: this only points at what it would refuse.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ResponseRule } from "@/lib/api/customTools";
import {
  emptyRule,
  MAX_RULES,
  messageProblem,
  ruleProblem,
  splitList,
  type RuleProblem,
  type RuleSource,
} from "@/lib/customTools/responseRules";

interface Props {
  rules: readonly ResponseRule[];
  onChange: (rules: ResponseRule[]) => void;
}

interface Row {
  id: number;
  rule: ResponseRule;
  /** "Success values" as typed. */
  values: string;
}

const NAME_PLACEHOLDER: Record<RuleSource, string> = {
  status: "",
  header: "X-Result-Code",
  json: "/status/code",
};

export function ResponseRulesField({ rules, onChange }: Props) {
  const { t } = useTranslation();
  const next = useRef(0);
  const make = (rule: ResponseRule): Row => ({
    id: next.current++,
    rule,
    values: rule.ok_values.join(", "),
  });
  const [rows, setRows] = useState<Row[]>(() => rules.map(make));
  const update = (list: Row[]) => {
    setRows(list);
    onChange(list.map((r) => ({ ...r.rule, ok_values: splitList(r.values) })));
  };
  const edit = (id: number, patch: Partial<Row>) =>
    update(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const editRule = (row: Row, patch: Partial<ResponseRule>) =>
    edit(row.id, { rule: { ...row.rule, ...patch } });

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row) => (
        <RuleRow
          key={row.id}
          row={row}
          onRule={(patch) => editRule(row, patch)}
          onValues={(values) => edit(row.id, { values })}
          onRemove={() => update(rows.filter((r) => r.id !== row.id))}
        />
      ))}
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto w-fit px-0 py-0.5"
        disabled={rows.length >= MAX_RULES}
        onClick={() => update([...rows, make({ ...emptyRule(), source: "header" })])}
      >
        <Plus aria-hidden />
        {t("customTools.responseRules.add")}
      </Button>
    </div>
  );
}

function RuleRow({
  row,
  onRule,
  onValues,
  onRemove,
}: {
  row: Row;
  onRule: (patch: Partial<ResponseRule>) => void;
  onValues: (values: string) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const { rule } = row;
  const isStatus = rule.source === "status";
  const problem = ruleProblem(rule);
  const message = messageProblem(rule);
  const text = (p: RuleProblem | null) => (p ? t(`customTools.responseRules.problem.${p}`) : null);
  const nameError = problem && problem !== "noValues" && problem !== "status" && problem !== "long";
  const valuesError = problem && !nameError ? problem : null;
  const messageSource = rule.message?.source ?? "none";

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border-subtle p-3">
      <div className="flex items-start gap-2">
        <Select
          value={rule.source}
          onValueChange={(source) =>
            onRule(
              source === "status"
                ? { source, name: "", missing: "ok" }
                : { source: source as RuleSource, name: isStatus ? "" : rule.name },
            )
          }
        >
          <SelectTrigger className="w-44" aria-label={t("customTools.responseRules.read")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(["status", "header", "json"] as const).map((s) => (
              <SelectItem key={s} value={s}>
                {t(`customTools.responseRules.source.${s}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {isStatus ? null : (
          <Input
            className="min-w-0 flex-1 font-mono"
            value={rule.name ?? ""}
            placeholder={NAME_PLACEHOLDER[rule.source]}
            aria-label={t("customTools.responseRules.name")}
            aria-invalid={nameError ? true : undefined}
            onChange={(e) => onRule({ name: e.target.value })}
          />
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon-md"
          className="ml-auto"
          aria-label={t("customTools.responseRules.remove")}
          onClick={onRemove}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
      {nameError ? (
        <p role="alert" className="text-xs text-danger">
          {text(problem)}
        </p>
      ) : null}
      <div className="flex items-start gap-2">
        <Input
          className="min-w-0 flex-1 font-mono"
          value={row.values}
          placeholder={isStatus ? "200, 204" : "OK, 0"}
          aria-label={t("customTools.responseRules.values")}
          aria-invalid={valuesError ? true : undefined}
          onChange={(e) => onValues(e.target.value)}
        />
        {isStatus ? null : (
          <Select
            value={rule.missing ?? "ok"}
            onValueChange={(missing) => onRule({ missing: missing as "ok" | "error" })}
          >
            <SelectTrigger className="w-44" aria-label={t("customTools.responseRules.missing")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ok">{t("customTools.responseRules.missingOk")}</SelectItem>
              <SelectItem value="error">{t("customTools.responseRules.missingError")}</SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>
      {valuesError ? (
        <p role="alert" className="text-xs text-danger">
          {text(valuesError)}
        </p>
      ) : null}
      <div className="flex items-start gap-2">
        <Select
          value={messageSource}
          onValueChange={(source) =>
            onRule({
              message:
                source === "none"
                  ? null
                  : { source: source as "header" | "json", name: rule.message?.name ?? "" },
            })
          }
        >
          <SelectTrigger className="w-44" aria-label={t("customTools.responseRules.message")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">{t("customTools.responseRules.messageNone")}</SelectItem>
            <SelectItem value="header">{t("customTools.responseRules.source.header")}</SelectItem>
            <SelectItem value="json">{t("customTools.responseRules.source.json")}</SelectItem>
          </SelectContent>
        </Select>
        {rule.message ? (
          <Input
            className="min-w-0 flex-1 font-mono"
            value={rule.message.name}
            placeholder={NAME_PLACEHOLDER[rule.message.source]}
            aria-label={t("customTools.responseRules.messageName")}
            aria-invalid={message ? true : undefined}
            onChange={(e) =>
              onRule({ message: { source: rule.message!.source, name: e.target.value } })
            }
          />
        ) : null}
      </div>
      {message ? (
        <p role="alert" className="text-xs text-danger">
          {text(message)}
        </p>
      ) : null}
    </div>
  );
}
