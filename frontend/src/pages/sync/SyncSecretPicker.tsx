// frontend/src/pages/sync/SyncSecretPicker.tsx
//
// The remote's Secret: a pick from the Secrets store, never a value. The
// field holds a REFERENCE the daemon resolves when it pulls and pushes, so no
// secret ever reaches this page, the repository's git config, or an error.
//
// A stored reference the store no longer lists (set from the CLI, or deleted
// since) stays selectable under its own name rather than vanishing from the
// field, so the form never silently changes what the remote uses.
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { displayName } from "@/components/secret/secretRows";
import { useSecrets } from "@/lib/hooks/useSecrets";

/** The option for "no secret" — an SSH remote may use the system's keys. */
const NONE = "__none__";

const SECRET_PICKER_ID = "sync-secret";

interface Props {
  value: string;
  onChange: (ref: string) => void;
  disabled?: boolean;
  /** Open the picker on mount — the sign-in failure's "Choose secret" lands here. */
  autoOpen?: boolean;
  describedBy?: string;
}

export function SyncSecretPicker({ value, onChange, disabled, autoOpen, describedBy }: Props) {
  const { t } = useTranslation();
  const { data } = useSecrets();
  const refs = data?.refs ?? [];

  const options: ComboboxOption[] = [
    { value: NONE, label: t("sync.remote.secretNone") },
    ...refs.map((r) => ({
      value: r.ref,
      label: displayName(r, t("secrets.unnamed")),
      hint: r.present ? undefined : t("sync.remote.secretMissing"),
    })),
  ];
  if (value && !refs.some((r) => r.ref === value)) {
    options.push({ value, label: t("secrets.unnamed"), hint: t("sync.remote.secretMissing") });
  }

  useEffect(() => {
    if (!autoOpen) return;
    const trigger = document.getElementById(SECRET_PICKER_ID);
    trigger?.scrollIntoView?.({ block: "center" });
    trigger?.focus();
    trigger?.click();
  }, [autoOpen]);

  return (
    <Combobox
      id={SECRET_PICKER_ID}
      value={value || NONE}
      options={options}
      onChange={(next) => onChange(next === NONE ? "" : next)}
      placeholder={t("sync.remote.secretPlaceholder")}
      emptyMessage={t("sync.remote.secretEmpty")}
      disabled={disabled}
      aria-describedby={describedBy}
    />
  );
}
