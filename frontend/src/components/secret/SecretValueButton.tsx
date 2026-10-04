// src/components/secret/SecretValueButton.tsx — a header / env row's value field
// (Foundations 0.2.05 · Header and env rows): plain text with a 🔑 button at its
// end that opens the secret menu; once a secret is chosen it reads "🔑 name ▾" (its label, not its id).
import { useTranslation } from "react-i18next";
import { ChevronDown, KeyRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { fieldClass } from "@/components/ui/field-classes";
import { Input } from "@/components/ui/input";
import { useSecretChoices } from "./useSecretChoices";
import type { RowValue } from "./secretValue";
import { cn } from "@/lib/utils";
import { SecretMenu } from "./SecretMenu";

interface Props {
  rowKey: string;
  value: RowValue;
  onChange: (value: RowValue) => void;
  /** Label a New secret starts with (from the row's key). */
  defaultLabel: string;
  autoFocus?: boolean;
}

export function SecretValueButton({ rowKey, value, onChange, defaultLabel, autoFocus }: Props) {
  const { t } = useTranslation();
  const { names, loaded, displayOf } = useSecretChoices();
  const label = rowKey || t("secretRows.value");
  const select = (name: string) => onChange({ kind: "stored", name });

  if (value.kind === "plain") {
    return (
      <div className="relative min-w-0">
        <Input
          aria-label={t("secretRows.valueOf", { key: label })}
          value={value.value}
          autoFocus={autoFocus}
          spellCheck={false}
          className="pr-8 font-mono text-xs"
          onChange={(e) => onChange({ kind: "plain", value: e.target.value })}
        />
        <SecretMenu selected={null} defaultNewLabel={defaultLabel} onSelectStored={select}>
          <button
            type="button"
            aria-label={t("secretRows.pick", { key: label })}
            title={t("secretRows.pickTitle")}
            className="absolute right-1 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover hover:text-text"
          >
            <KeyRound className="size-3.5" aria-hidden />
          </button>
        </SecretMenu>
      </div>
    );
  }

  const shown = value.kind === "new" ? value.label : displayOf(value.name);
  const missing = value.kind === "stored" && loaded && !names.has(value.name);
  return (
    <SecretMenu
      selected={value.name}
      defaultNewLabel={defaultLabel}
      onSelectStored={select}
      onPlain={() => onChange({ kind: "plain", value: "" })}
      pendingLabel={
        value.kind === "new"
          ? { value: value.label, onChange: (label) => onChange({ ...value, label }) }
          : undefined
      }
    >
      <button
        type="button"
        aria-label={t("secretField.chosen", { label, name: shown })}
        className={cn(
          fieldClass,
          "flex h-control-md min-w-0 items-center gap-2 px-2.5 py-0 text-left",
        )}
      >
        <KeyRound className="size-[13px] shrink-0 text-text-muted" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-xs">{shown}</span>
        {value.kind === "new" ? (
          <Badge variant="secondary" className="shrink-0 font-sans">
            {t("secretField.newBadge")}
          </Badge>
        ) : null}
        {missing ? (
          <Badge variant="warning" className="shrink-0 font-sans">
            {t("secretField.missing")}
          </Badge>
        ) : null}
        <ChevronDown className="size-[13px] shrink-0 text-text-subtle" aria-hidden />
      </button>
    </SecretMenu>
  );
}
