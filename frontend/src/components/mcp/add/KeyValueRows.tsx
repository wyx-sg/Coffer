// frontend/src/components/mcp/add/KeyValueRows.tsx — editable KEY / value rows,
// each marked Secret or Plain: a stdio server's environment, an HTTP server's
// headers (boards Mcp-EditStdio / Mcp-Edit / Mcp-Add-TestPassed). Shared by the
// Add server form and the edit dialog.
//
// A Plain row holds its value. A Secret row holds a typed value for a new
// secret — or, with `storedSecrets` on (the edit dialog), may cite a stored
// secret instead (`ParsedEnvVar.ref`, see `components/mcp/env/SecretValueCell`).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { Segmented } from "@/components/ui/segmented";
import { useSecretNames } from "@/lib/hooks/useSecretNames";
import type { ParsedEnvVar } from "@/lib/mcp/pasteParse";
import { SecretValueCell } from "../env/SecretValueCell";

type Kind = "secret" | "plain";

interface Props {
  idPrefix: string;
  /** The section's label ("Environment" / "Headers"). */
  label: string;
  rows: ParsedEnvVar[];
  onChange: (rows: ParsedEnvVar[]) => void;
  keyPlaceholder: string;
  /** Let a Secret row cite a stored secret (its own, or one on the Secrets
   *  page) instead of a typed value. Off in the Add form. */
  storedSecrets?: boolean;
  /** Index of a row whose value input takes focus when first shown. */
  focusRow?: number;
  /** The add button's label; defaults to "Add variable". */
  addLabel?: string;
}

export function KeyValueRows(props: Props) {
  const { idPrefix, label, rows, onChange, keyPlaceholder, storedSecrets = false } = props;
  const { t } = useTranslation();
  const [focusRow, setFocusRow] = useState<number | undefined>(props.focusRow);
  const update = (i: number, patch: Partial<ParsedEnvVar>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const kinds = [
    { value: "secret" as const, label: t("mcp.add.secret") },
    { value: "plain" as const, label: t("mcp.env.plain") },
  ];
  return (
    <div className="space-y-2">
      <Label className="block">{label}</Label>
      {rows.map((row, i) => {
        const key = row.key || label;
        return (
          <div key={`${idPrefix}-${i}`} className="space-y-1">
            <div className="flex items-center gap-2">
              <Input
                aria-label={t("mcp.add.rowKey", { label })}
                value={row.key}
                placeholder={keyPlaceholder}
                className="min-w-0 flex-1 font-mono text-xs"
                spellCheck={false}
                onChange={(e) => update(i, { key: e.target.value })}
              />
              <Segmented<Kind>
                label={t("mcp.env.kindFor", { key })}
                value={row.isSecret ? "secret" : "plain"}
                options={kinds}
                className="h-control-md items-center"
                onChange={(k) => update(i, { isSecret: k === "secret" })}
              />
              <ValueCell
                row={row}
                label={label}
                storedSecrets={storedSecrets}
                autoFocus={focusRow === i}
                onChange={(patch) => update(i, patch)}
                onReplace={() => setFocusRow(i)}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("mcp.add.removeRow", { key })}
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
              >
                <Trash2 />
              </Button>
            </div>
            {row.isSecret &&
            row.key.trim() !== "" &&
            row.value === "" &&
            !row.ref &&
            !row.storedRef ? (
              <p className="text-xs text-text-muted">
                {t("mcp.add.secretMissing", { key: row.key })}
              </p>
            ) : null}
          </div>
        );
      })}
      <div className="space-y-1">
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto px-0 py-0.5"
          onClick={() => onChange([...rows, { key: "", value: "", isSecret: false }])}
        >
          <Plus /> {props.addLabel ?? t("mcp.env.addVariable")}
        </Button>
        <p className="text-xs text-text-muted">{t("mcp.env.hint")}</p>
      </div>
    </div>
  );
}

interface CellProps {
  row: ParsedEnvVar;
  label: string;
  storedSecrets: boolean;
  autoFocus: boolean;
  onChange: (patch: Partial<ParsedEnvVar>) => void;
  onReplace: () => void;
}

function ValueCell({ row, label, storedSecrets, autoFocus, onChange, onReplace }: CellProps) {
  const { t } = useTranslation();
  const key = row.key || label;
  if (!row.isSecret) {
    return (
      <Input
        aria-label={t("mcp.add.rowValue", { key })}
        value={row.value}
        className="min-w-0 flex-[1.3] font-mono text-xs"
        spellCheck={false}
        onChange={(e) => onChange({ value: e.target.value })}
      />
    );
  }
  if (storedSecrets) {
    return (
      <StoredCell
        row={row}
        label={label}
        autoFocus={autoFocus}
        onChange={onChange}
        onReplace={onReplace}
      />
    );
  }
  return (
    <PasswordInput
      aria-label={t("mcp.add.rowValue", { key })}
      containerClassName="min-w-0 flex-[1.3]"
      value={row.value}
      placeholder={t("mcp.add.secretValue")}
      onChange={(e) => onChange({ value: e.target.value })}
    />
  );
}

/** The picker cell, with the Secrets-page list — fetched only where it is on. */
function StoredCell(props: Omit<CellProps, "storedSecrets">) {
  const { names, data } = useSecretNames();
  const present = data ? new Set(data.refs.filter((r) => r.present).map((r) => r.ref)) : undefined;
  return <SecretValueCell {...props} secretNames={names} present={present} />;
}
