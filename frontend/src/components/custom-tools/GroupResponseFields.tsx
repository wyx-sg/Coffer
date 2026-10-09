// src/components/custom-tools/GroupResponseFields.tsx — Edit group's Response section: the extra response headers
// reported with a call, and the rules every answer of the group must satisfy.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import type { ResponseRule } from "@/lib/api/customTools";
import { diagnosticHeadersProblem, splitList } from "@/lib/customTools/responseRules";
import { FormField } from "./FormField";
import { ResponseRulesField } from "./ResponseRulesField";

interface Props {
  headers: string;
  onHeaders: (text: string) => void;
  rules: readonly ResponseRule[];
  onRules: (rules: ResponseRule[]) => void;
}

export function GroupResponseFields({ headers, onHeaders, rules, onRules }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const problem = diagnosticHeadersProblem(splitList(headers));
  return (
    <>
      <FormField
        label={t("customTools.editGroup.diagnosticHeaders")}
        htmlFor={`${id}-diag`}
        help={t("customTools.editGroup.diagnosticHeadersHelp")}
        error={problem ? t(`customTools.editGroup.diagnosticProblem.${problem}`) : undefined}
      >
        <Input
          id={`${id}-diag`}
          className="font-mono"
          value={headers}
          placeholder="X-Trace-Id, X-Error-Code"
          onChange={(e) => onHeaders(e.target.value)}
        />
      </FormField>
      <FormField
        label={t("customTools.editGroup.responseRules")}
        help={t("customTools.editGroup.responseRulesHelp")}
      >
        <ResponseRulesField rules={rules} onChange={onRules} />
      </FormField>
    </>
  );
}
