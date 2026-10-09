// src/components/settings/security/ImportedKeyResult.tsx — the answer an import gives.
//
// Spec secret "Import a master key after showing whose key it is": the key
// this Mac now uses, how many stored secrets it decrypts, and — when some were
// stored here with the old key — their names, with a way to the Secrets page to
// add their values again.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { KeyImport } from "@/lib/api/security";

import { formatFingerprint, secretName } from "./fingerprint";

export function ImportedKeyResult({ result, onDone }: { result: KeyImport; onDone: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fingerprint = formatFingerprint(result.fingerprint);
  const locked = result.locked_refs.map(secretName);

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("settings.security.import.importedTitle")}</DialogTitle>
        <DialogDescription>
          {locked.length > 0
            ? t("settings.security.import.importedLocked", { fingerprint, count: locked.length })
            : t("settings.security.import.importedAll", { fingerprint })}
        </DialogDescription>
      </DialogHeader>
      <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
        <dt className="text-xs text-text-muted">{t("settings.security.import.readable")}</dt>
        <dd className="text-text" data-testid="readable-now">
          {t("settings.security.import.secretCount", { count: result.readable })}
        </dd>
        {locked.length > 0 ? (
          <>
            <dt className="text-xs text-text-muted">{t("settings.security.import.stillLocked")}</dt>
            <dd className="min-w-0 font-mono text-xs text-text" data-testid="still-locked">
              {locked.join(", ")}
            </dd>
          </>
        ) : null}
      </dl>
      {locked.length > 0 ? (
        <p className="text-xs text-text-muted">{t("settings.security.import.lockedHint")}</p>
      ) : null}
      <DialogFooter>
        {locked.length > 0 ? (
          <Button
            variant="outline"
            // Replace the Settings entry, as the footer link does: Back returns
            // to where Settings was opened from.
            onClick={() => navigate("/secrets", { replace: true })}
          >
            {t("settings.security.import.openSecrets")}
          </Button>
        ) : null}
        <Button onClick={onDone}>{t("common.done")}</Button>
      </DialogFooter>
    </>
  );
}
