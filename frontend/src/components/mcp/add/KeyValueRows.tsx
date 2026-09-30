// frontend/src/components/mcp/add/KeyValueRows.tsx — editable KEY / value rows
// with an optional Secret toggle: a stdio server's environment, an HTTP
// server's headers. Used by the Add server form and by the edit dialog (which
// keeps stored secrets in CredentialRowEditor and so turns the toggle off).
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { Switch } from "@/components/ui/switch";
import type { ParsedEnvVar } from "@/lib/mcp/pasteParse";

interface Props {
  idPrefix: string;
  /** The section's label ("Environment" / "Headers"). */
  label: string;
  rows: ParsedEnvVar[];
  onChange: (rows: ParsedEnvVar[]) => void;
  /** Offer the Secret toggle (the add form); off in the edit dialog. */
  secretToggle?: boolean;
  keyPlaceholder: string;
}

export function KeyValueRows({
  idPrefix,
  label,
  rows,
  onChange,
  secretToggle = true,
  keyPlaceholder,
}: Props) {
  const { t } = useTranslation();
  const update = (i: number, patch: Partial<ParsedEnvVar>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {rows.map((row, i) => (
        <div key={`${idPrefix}-${i}`} className="space-y-1">
          <div className="flex items-center gap-2">
            <Input
              aria-label={t("mcp.add.rowKey", { label })}
              value={row.key}
              placeholder={keyPlaceholder}
              className="flex-1 font-mono text-xs"
              spellCheck={false}
              onChange={(e) => update(i, { key: e.target.value })}
            />
            {row.isSecret ? (
              <PasswordInput
                aria-label={t("mcp.add.rowValue", { key: row.key || label })}
                containerClassName="flex-1"
                value={row.value}
                placeholder={t("mcp.add.secretValue")}
                onChange={(e) => update(i, { value: e.target.value })}
              />
            ) : (
              <Input
                aria-label={t("mcp.add.rowValue", { key: row.key || label })}
                value={row.value}
                className="flex-1 font-mono text-xs"
                spellCheck={false}
                onChange={(e) => update(i, { value: e.target.value })}
              />
            )}
            {secretToggle ? (
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-text-muted">
                <Switch
                  checked={row.isSecret}
                  aria-label={t("mcp.add.secretFor", { key: row.key || label })}
                  onCheckedChange={(on) => update(i, { isSecret: on })}
                />
                {t("mcp.add.secret")}
              </label>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("mcp.add.removeRow", { key: row.key || label })}
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
            >
              <Trash2 />
            </Button>
          </div>
          {row.isSecret && secretToggle ? (
            <p className="text-xs text-text-muted">
              {row.value === ""
                ? t("mcp.add.secretMissing", { key: row.key })
                : t("mcp.add.secretHint")}
            </p>
          ) : null}
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...rows, { key: "", value: "", isSecret: false }])}
      >
        <Plus /> {t("mcp.add.addRow")}
      </Button>
    </div>
  );
}
