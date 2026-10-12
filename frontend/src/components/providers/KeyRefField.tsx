// src/components/providers/KeyRefField.tsx — the Edit dialog's API key: the secret it names, and Replace in place.
//
// The key is write-only, so the row names its secret and never the value.
// Replace opens the same fields the Replace dialog shows (ReplaceSecretFields)
// right under it; whatever is entered there is saved with the rest of the form,
// and Keep current key folds them away again with nothing changed.
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SecretNameLink } from "@/components/secret/SecretNameLink";
import { ReplaceSecretFields, type ReplaceDraft } from "@/components/secret/ReplaceSecretFields";

interface Props {
  secretRef: string | null;
  /** The entered replacement, or null while the key stays as it is. */
  draft: ReplaceDraft | null;
  onDraftChange: (draft: ReplaceDraft | null) => void;
  disabled?: boolean;
}

export function KeyRefField({ secretRef, draft, onDraftChange, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-label text-text">{t("providers.fields.apiKey")}</span>
      {secretRef ? (
        <>
          <div
            aria-label={t("providers.key.secretLabel")}
            className="flex h-control-md items-center gap-1.5 rounded-md border border-border bg-surface-sunken px-2.5"
          >
            <KeyRound className="size-3.5 text-text-muted" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-xs">
              <SecretNameLink secretRef={secretRef} />
            </span>
            {draft === null ? (
              <span className="inline-flex h-[18px] items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
                {t("providers.key.storedChip")}
              </span>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="-mr-1.5 h-6 px-2 text-xs"
              disabled={disabled}
              onClick={() =>
                onDraftChange(draft === null ? { source: "value", value: "", picked: "" } : null)
              }
            >
              {draft === null ? t("secretRef.replace") : t("secretRef.keep")}
            </Button>
          </div>
          {draft === null ? (
            <p className="text-xs text-text-muted">{t("providers.edit.keyHint")}</p>
          ) : (
            <div className="mt-1.5">
              <ReplaceSecretFields
                currentRef={secretRef}
                draft={draft}
                onChange={onDraftChange}
                showCurrent={false}
                valueHint={t("providers.edit.replaceHint")}
                defaultNewLabel={t("providers.fields.apiKey")}
                disabled={disabled}
                autoFocus
              />
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-text-muted">{t("providers.key.none")}</p>
      )}
    </div>
  );
}
