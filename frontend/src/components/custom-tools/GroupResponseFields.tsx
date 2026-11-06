// src/components/custom-tools/GroupResponseFields.tsx — Edit group's Response section: the rules every
// answer of the group must satisfy. (A test reports every response header, so there is nothing to pick.)
import { useTranslation } from "react-i18next";

import type { ResponseRule } from "@/lib/api/customTools";
import { FormField } from "./FormField";
import { ResponseRulesField } from "./ResponseRulesField";

interface Props {
  rules: readonly ResponseRule[];
  onRules: (rules: ResponseRule[]) => void;
}

export function GroupResponseFields({ rules, onRules }: Props) {
  const { t } = useTranslation();
  return (
    <FormField
      label={t("customTools.editGroup.responseRules")}
      help={t("customTools.editGroup.responseRulesHelp")}
    >
      <ResponseRulesField rules={rules} onChange={onRules} />
    </FormField>
  );
}
