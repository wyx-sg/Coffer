// frontend/src/components/mcp/env/EnvRowsField.tsx — a server's Environment
// (stdio) or Headers (HTTP) as the Add form and the Edit dialog show them
// (boards Mcp-EditStdio / Mcp-Edit / Mcp-Add-TestPassed): the label, the shared
// header / env rows, and the line saying secrets stay in Coffer.
import { useTranslation } from "react-i18next";

import { KeyValueSecretRows } from "@/components/secret/KeyValueSecretRows";
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import { Label } from "@/components/ui/label";

interface Props {
  http: boolean;
  rows: KeyValueSecretRow[];
  onChange: (rows: KeyValueSecretRow[]) => void;
  /** Index of a row whose value takes focus when first shown. */
  focusRow?: number;
}

export function EnvRowsField({ http, rows, onChange, focusRow }: Props) {
  const { t } = useTranslation();
  const label = http ? t("mcp.add.headers") : t("mcp.add.env");
  return (
    <div className="space-y-2">
      <Label className="block">{label}</Label>
      <KeyValueSecretRows
        rows={rows}
        onChange={onChange}
        label={label}
        keyPlaceholder={http ? "Authorization" : "API_KEY"}
        addLabel={http ? t("mcp.env.addHeader") : t("mcp.env.addVariable")}
        focusRow={focusRow}
        schemes={http}
      />
      <p className="text-xs text-text-muted">
        {rows.length === 0 ? `${t("mcp.env.none")} ` : ""}
        {t(http ? "mcp.env.hintHeaders" : "mcp.env.hint")}
      </p>
    </div>
  );
}
