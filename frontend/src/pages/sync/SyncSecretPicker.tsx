// frontend/src/pages/sync/SyncSecretPicker.tsx
//
// The remote's Secret: the one secret field (Foundations 0.2.05), so the push
// token is picked from Secrets, pasted as a new one, or made with New secret…,
// and the field holds a REFERENCE the daemon resolves when it pulls and pushes.
// No secret ever reaches the repository's git config or an error. An SSH
// remote may use the system's keys, so the menu also offers None.
//
// A stored reference the store no longer lists (set from the CLI, or deleted
// since) stays in the field under its own name with a Missing mark rather than
// vanishing, so the form never silently changes what the remote uses.
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { SecretField } from "@/components/secret/SecretField";
import type { SecretFieldValue } from "@/lib/secretValue";

const SECRET_PICKER_ID = "sync-secret";

interface Props {
  value: SecretFieldValue;
  onChange: (value: SecretFieldValue) => void;
  disabled?: boolean;
  /** Open the picker on mount — the sign-in failure's "Choose secret" lands here. */
  autoOpen?: boolean;
}

export function SyncSecretPicker({ value, onChange, disabled, autoOpen }: Props) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!autoOpen) return;
    const field = document.getElementById(SECRET_PICKER_ID);
    field?.scrollIntoView?.({ block: "center" });
    field?.focus();
    // A chosen secret's trigger opens its menu; an empty field takes a paste where it is.
    if (field instanceof HTMLButtonElement) field.click();
  }, [autoOpen]);

  return (
    <div className="w-full">
      <SecretField
        id={SECRET_PICKER_ID}
        value={value}
        onChange={onChange}
        defaultName={t("sync.remote.secretDefaultName")}
        clearLabel={t("sync.remote.secretNone")}
        aria-label={t("sync.remote.secret")}
        disabled={disabled}
        help={false}
      />
    </div>
  );
}
