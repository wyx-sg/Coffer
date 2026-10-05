// src/components/custom-tools/GroupHeaderRows.tsx — "Headers" of a group being made: the shared key · value ·
// delete rows (a secret only from Coffer) with one line of help below.
import { useTranslation } from "react-i18next";

import { KeyValueSecretRows } from "@/components/secret/KeyValueSecretRows";
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import { Label } from "@/components/ui/label";

interface Props {
  rows: KeyValueSecretRow[];
  onChange: (rows: KeyValueSecretRow[]) => void;
  /** The line under the rows. */
  help: string;
  /** Name a new secret after the group: `<group>-<header>`. */
  group: string;
}

export function GroupHeaderRows({ rows, onChange, help, group }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{t("customTools.fields.headers")}</Label>
      <KeyValueSecretRows
        rows={rows}
        onChange={onChange}
        label={t("customTools.fields.headers")}
        keyPlaceholder={t("customTools.editor.headerKey")}
        addLabel={t("customTools.editor.addHeader")}
        secretLabelFor={(key) => [group, key].filter(Boolean).join("-")}
      />
      <p className="text-xs text-text-muted">{help}</p>
    </div>
  );
}
