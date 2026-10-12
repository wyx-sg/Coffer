// src/components/secret/ReplaceSecretFields.tsx — the one way to replace the secret a field uses.
//
// The Replace dialog and an Edit dialog's inline "Replace" show these same fields:
// the current secret (and who else uses it), then **Enter a new value** or
// **Use another secret**. A new value is written into the secret the field uses
// now, so everything else that cites it gets the value too; another secret
// re-points only this field and leaves the old secret as it is. The value field
// starts empty and never shows the old value. ADR unify-secret-replacement.
import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { Segmented } from "@/components/ui/segmented";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { NewSecretDialog } from "./NewSecretDialog";
import { SecretNameLink } from "./SecretNameLink";
import { citersOf, SECRET_PREFIX } from "./secretRows";
import { useKindLabel } from "./useKindLabel";
import { useSecretChoices } from "./useSecretChoices";
import { useShownCiter } from "./useShownCiter";

export type SecretSource = "value" | "existing";

/** What the person has entered so far: a new value, or another stored secret (`secret/<id>`). */
export interface ReplaceDraft {
  source: SecretSource;
  value: string;
  picked: string;
}

export const EMPTY_DRAFT: ReplaceDraft = { source: "value", value: "", picked: "" };

/** The draft says what to do: a non-empty value, or a picked secret. */
export function draftReady(draft: ReplaceDraft): boolean {
  return draft.source === "value" ? draft.value !== "" : draft.picked !== "";
}

interface Props {
  /** The ref the field uses now. */
  currentRef: string;
  draft: ReplaceDraft;
  onChange: (draft: ReplaceDraft) => void;
  /** Offer "Use another secret" — only where the caller can re-point the field. */
  allowExisting?: boolean;
  /** Show the "Current secret" row; an Edit dialog shows its own. */
  showCurrent?: boolean;
  /** The value field's label; "New value" by default. */
  valueLabel?: string;
  /** The line under the value field; the write-only note by default. */
  valueHint?: string;
  /** Under the value field — a check of the pasted value (a provider's models, a bot's handle). */
  check?: ReactNode;
  /** Label a New secret… starts with. */
  defaultNewLabel?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  /** A link to the Secrets page was followed — a dialog closes itself. */
  onNavigate?: () => void;
}

const TERM = "text-xs font-label text-text";

export function ReplaceSecretFields({
  currentRef,
  draft,
  onChange,
  allowExisting = true,
  showCurrent = true,
  valueLabel,
  valueHint,
  check,
  defaultNewLabel = "",
  disabled,
  autoFocus,
  onNavigate,
}: Props) {
  const { t } = useTranslation();
  const valueId = useId();
  const pickId = useId();
  const kindLabel = useKindLabel();
  const shown = useShownCiter();
  const { data } = useSecrets();
  const { options } = useSecretChoices();
  const [creating, setCreating] = useState(false);
  const row = data?.refs.find((r) => r.ref === currentRef);
  const users = row ? citersOf(row).map(shown) : [];
  const others = options.filter((o) => `${SECRET_PREFIX}${o.name}` !== currentRef);
  const source = allowExisting ? draft.source : "value";

  return (
    <div className="flex flex-col gap-3">
      {showCurrent ? (
        <div className="flex flex-col gap-1.5">
          <span className={TERM}>{t("secretRef.current")}</span>
          <span className="inline-flex items-center gap-1.5">
            <KeyRound className="size-3.5 text-text-muted" aria-hidden />
            <SecretNameLink secretRef={currentRef} className="text-xs" onNavigate={onNavigate} />
          </span>
        </div>
      ) : null}
      {allowExisting ? (
        <Segmented<SecretSource>
          label={t("secretRef.source")}
          value={source}
          disabled={disabled}
          onChange={(next) => onChange({ ...draft, source: next })}
          options={[
            { value: "value", label: t("secretRef.newValue") },
            { value: "existing", label: t("secretRef.useExisting") },
          ]}
        />
      ) : null}
      {source === "value" ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={valueId} required>
            {valueLabel ?? t("secretRef.valueLabel")}
          </Label>
          <PasswordInput
            id={valueId}
            value={draft.value}
            autoComplete="off"
            autoFocus={autoFocus}
            disabled={disabled}
            className="font-mono text-xs"
            onChange={(e) => onChange({ ...draft, value: e.target.value })}
          />
          <p className="text-xs text-text-muted">{valueHint ?? t("secretRef.valueHint")}</p>
          {users.length > 1 ? (
            <p className="text-xs text-text-muted">
              {t("secretRef.shared", {
                users: users.map((c) => `${kindLabel(c.kind)} ${c.name}`).join(", "),
              })}
            </p>
          ) : null}
          {check}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={pickId} required>
            {t("secretRef.pickLabel")}
          </Label>
          <Combobox
            id={pickId}
            value={draft.picked || null}
            options={others.map((o) => ({
              value: `${SECRET_PREFIX}${o.name}`,
              label: o.display,
              hint: o.usedBy ? t("secretField.usedBy", { count: o.usedBy }) : undefined,
            }))}
            onChange={(picked) => onChange({ ...draft, picked })}
            placeholder={t("secretRef.pickPlaceholder")}
            emptyMessage={t("secretRef.pickEmpty")}
            disabled={disabled}
          />
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs text-text-muted">{t("secretRef.existingHint")}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="shrink-0"
              disabled={disabled}
              onClick={() => setCreating(true)}
            >
              <Plus aria-hidden /> {t("secretField.newSecret")}
            </Button>
          </div>
          <NewSecretDialog
            open={creating}
            onOpenChange={setCreating}
            defaultLabel={defaultNewLabel}
            onCreated={(name) => onChange({ ...draft, picked: `${SECRET_PREFIX}${name}` })}
          />
        </div>
      )}
    </div>
  );
}
