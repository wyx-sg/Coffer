// src/components/secret/KeyValueSecretRows.tsx — the one header / env row list
// (Foundations 0.2.05 · Header and env rows): key · value · delete, fixed
// columns so rows align. MCP env and headers, and a custom-tool group's headers,
// share it. Secrets only come from Coffer (principle 22): see `SecretValueButton`.
//
// Controlled: `rows` in, `onChange(rows)` out. On submit, call
// `persistNewSecrets(rows.map((r) => r.value))` before saving the form.
import { useTranslation } from "react-i18next";
import { KeyRound, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSecretChoices } from "./useSecretChoices";
import { schemeOfRow, storePlainRow, withScheme } from "@/lib/authScheme";
import { looksLikeSecret, type KeyValueSecretRow } from "./secretValue";
import { AuthSchemeSelect } from "./AuthSchemeSelect";
import { SecretValueButton } from "./SecretValueButton";

interface Props {
  rows: KeyValueSecretRow[];
  onChange: (rows: KeyValueSecretRow[]) => void;
  /** The section's label ("Headers" / "Environment"), used in accessible names. */
  label: string;
  keyPlaceholder: string;
  /** Add button label ("Add header"); defaults to "Add variable". */
  addLabel?: string;
  /** Read-only form: rows render as `key ← 🔑 name`. */
  readOnly?: boolean;
  /** Labels a New secret from a row's key; defaults to the key. */
  secretLabelFor?: (key: string) => string;
  /** Index of a row whose value takes focus when first shown. */
  focusRow?: number;
  /** HTTP headers: a secret row names the auth scheme Coffer puts in front of it when sending. */
  schemes?: boolean;
}

const GRID = "grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_26px] items-center gap-2";

export function KeyValueSecretRows(props: Props) {
  const { rows, onChange, label, keyPlaceholder, readOnly = false, focusRow, schemes } = props;
  const { t } = useTranslation();
  const { displayOf } = useSecretChoices();
  const labelFor = (key: string) => props.secretLabelFor?.(key) ?? key;
  const update = (i: number, patch: Partial<KeyValueSecretRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  if (readOnly) {
    return (
      <dl className="space-y-1.5">
        {rows.map((row, i) => (
          <div key={i} className="flex min-w-0 items-center gap-2 font-mono text-xs">
            <dt className="shrink-0 text-text">{row.key}</dt>
            <dd className="flex min-w-0 items-center gap-1.5 text-text-muted">
              {row.value.kind === "plain" ? (
                <span className="truncate">{row.value.value}</span>
              ) : (
                <>
                  <span aria-label={t("secretRows.readsFrom")}>←</span>
                  <KeyRound className="size-3.5 shrink-0" aria-hidden />
                  <span className="truncate text-text">
                    {row.value.kind === "new" ? row.value.label : displayOf(row.value.name)}
                  </span>
                </>
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return (
    <div className="space-y-2">
      {rows.map((row, i) => {
        const key = row.key || label;
        const hint = row.value.kind === "plain" && looksLikeSecret(row.key, row.value.value);
        return (
          <div key={i} className="space-y-1">
            <div className={GRID}>
              <Input
                aria-label={t("secretRows.keyOf", { label })}
                value={row.key}
                placeholder={keyPlaceholder}
                spellCheck={false}
                className="font-mono text-xs"
                onChange={(e) => update(i, { key: e.target.value })}
              />
              {schemes && row.value.kind !== "plain" ? (
                <div className="flex min-w-0 items-center gap-1.5">
                  <AuthSchemeSelect
                    rowKey={key}
                    value={schemeOfRow(row)}
                    onChange={(scheme) =>
                      onChange(rows.map((r, j) => (j === i ? withScheme(r, scheme) : r)))
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <SecretValueButton
                      rowKey={row.key}
                      value={row.value}
                      defaultLabel={labelFor(row.key)}
                      autoFocus={focusRow === i}
                      onChange={(value) => update(i, { value })}
                    />
                  </div>
                </div>
              ) : (
                <SecretValueButton
                  rowKey={row.key}
                  value={row.value}
                  defaultLabel={labelFor(row.key)}
                  autoFocus={focusRow === i}
                  onChange={(value) => update(i, { value })}
                />
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("secretRows.remove", { key })}
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
              >
                <Trash2 />
              </Button>
            </div>
            {hint && row.value.kind === "plain" ? (
              <p className="flex items-center gap-2 text-xs text-text-muted">
                {t("secretRows.storeHint")}
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0"
                  onClick={() =>
                    onChange(
                      rows.map((r, j) =>
                        j === i ? storePlainRow(r, labelFor(row.key), schemes === true) : r,
                      ),
                    )
                  }
                >
                  {t("secretRows.storeIt", { key })}
                </Button>
              </p>
            ) : null}
          </div>
        );
      })}
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto px-0 py-0.5"
        onClick={() => onChange([...rows, { key: "", value: { kind: "plain", value: "" } }])}
      >
        <Plus /> {props.addLabel ?? t("secretRows.addVariable")}
      </Button>
    </div>
  );
}
