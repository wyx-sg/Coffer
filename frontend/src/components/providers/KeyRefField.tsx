// src/components/providers/KeyRefField.tsx — the Edit dialog's read-only API key row: the secret it names, never the value.
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";
import { SecretNameLink } from "@/components/secret/SecretNameLink";

export function KeyRefField({ secretRef }: { secretRef: string | null }) {
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
            <span className="inline-flex h-[18px] items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
              {t("providers.key.storedChip")}
            </span>
          </div>
          <p className="text-xs text-text-muted">{t("providers.edit.keyHint")}</p>
        </>
      ) : (
        <p className="text-xs text-text-muted">{t("providers.key.none")}</p>
      )}
    </div>
  );
}
