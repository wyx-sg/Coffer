// src/components/custom-tools/GroupDescriptionField.tsx — a group's description: what the API is for. Agents read
// it beside each of the group's tools when they search for one (spec mcp-gateway "Describe a custom-tool group").
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Textarea } from "@/components/ui/textarea";
import { FormField } from "./FormField";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export function GroupDescriptionField({ value, onChange }: Props) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <FormField
      label={t("customTools.editGroup.description")}
      htmlFor={id}
      help={t("customTools.editGroup.descriptionHelp")}
    >
      <Textarea
        id={id}
        className="min-h-[58px]"
        rows={2}
        maxLength={2000}
        placeholder={t("customTools.editGroup.descriptionPlaceholder")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </FormField>
  );
}
