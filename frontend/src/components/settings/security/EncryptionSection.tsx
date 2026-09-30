// src/components/settings/security/EncryptionSection.tsx — Settings › Security › Encryption.
//
// Where the master key lives, whether Coffer could read it, and — in a
// development build only — the switch that moves it between a file beside
// the database and the login keychain (spec secret "Keep the master key
// behind a storage port chosen by the build"). A signed release keeps the key
// in its Keychain access group and nowhere else, so it has nothing to move.
//
// Moving the key re-stores it and changes what macOS asks on every daemon
// start, so the switch confirms first, and the confirmation closes only once
// the move went through.
//
// Below those: the key backup (desktop app only), the import of a key from
// another Mac, and the key's fingerprint, grouped in fours so two Macs can be
// compared at a glance.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import {
  useSecretSettings,
  useUpdateSecretSettings,
} from "@/lib/hooks/useSecretSettings";

import { useMasterKeyFingerprint } from "@/lib/hooks/useSecurity";

import { formatFingerprint } from "./fingerprint";
import { ImportKeyRow } from "./ImportKeyRow";
import { MasterKeyBackupRow } from "./MasterKeyBackupRow";
import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";

type Storage = "file" | "keychain";

export function EncryptionSection() {
  const { t } = useTranslation();
  const { data, isPending, error } = useSecretSettings();

  return (
    <SettingsSection title={t("settings.security.encryption.title")}>
      {isPending ? (
        <div className="py-3">
          <Skeleton className="h-10 w-full" />
        </div>
      ) : error ? (
        <p className="py-3 text-sm text-danger" role="alert">
          {translateApiError(t, error)}
        </p>
      ) : (
        <KeyRows storage={data!.master_key_storage ?? null} />
      )}
      <MasterKeyBackupRow />
      <ImportKeyRow />
      <FingerprintRow />
    </SettingsSection>
  );
}

function FingerprintRow() {
  const { t } = useTranslation();
  const { data } = useMasterKeyFingerprint();
  return (
    <SettingRow
      label={t("settings.security.fingerprint.title")}
      description={t("settings.security.fingerprint.description")}
    >
      <code className="font-mono text-sm text-text" data-testid="key-fingerprint">
        {data?.fingerprint
          ? formatFingerprint(data.fingerprint)
          : data
            ? t("settings.security.fingerprint.none")
            : "—"}
      </code>
    </SettingRow>
  );
}

function KeyRows({ storage }: { storage: string | null }) {
  const { t } = useTranslation();
  // `keychain_access_group` is the signed release's arrangement; anything else
  // is a development build (the manager's own definition of `development`).
  const signed = storage === "keychain_access_group";
  const inFile = storage === "file";

  return (
    <>
      <SettingRow
        label={
          inFile
            ? t("settings.security.masterKey.fileTitle")
            : t("settings.security.masterKey.keychainTitle")
        }
        description={
          inFile
            ? t("settings.security.masterKey.fileDescription")
            : t("settings.security.masterKey.keychainDescription")
        }
        status={
          // A signed release reads as the design draws it: the row and OK.
          // Only a development build carries a note, because its key is
          // weaker than the release's.
          signed ? null : (
            <span className={cn("text-xs", toneTextClass("warn"))}>
              {inFile
                ? t("settings.security.masterKey.developmentFile")
                : t("settings.security.masterKey.developmentKeychain")}
            </span>
          )
        }
      >
        <StatusWord tone="ok">{t("settings.security.masterKey.ok")}</StatusWord>
      </SettingRow>
      {signed ? null : <MoveKeyRow isKeychain={!inFile} />}
    </>
  );
}

function MoveKeyRow({ isKeychain }: { isKeychain: boolean }) {
  const { t } = useTranslation();
  const update = useUpdateSecretSettings();
  // The storage the user asked to move to, while the confirmation is open.
  const [target, setTarget] = useState<Storage | null>(null);
  const confirmKey = target === "keychain" ? "confirmKeychain" : "confirmFile";

  return (
    <SettingRow
      label={t("settings.security.masterKey.toggle")}
      labelFor="master-key-keychain"
      description={
        isKeychain
          ? t("settings.security.masterKey.keychainNote")
          : t("settings.security.masterKey.fileNote")
      }
      status={
        // The failure is shown in the dialog while it is open; once it is
        // dismissed, here, so a refused move never passes silently.
        update.isError && target === null ? (
          <span className="text-xs text-danger" role="alert">
            {translateApiError(t, update.error)}
          </span>
        ) : null
      }
    >
      <Switch
        id="master-key-keychain"
        checked={isKeychain}
        disabled={update.isPending}
        onCheckedChange={(checked) => {
          update.reset();
          setTarget(checked ? "keychain" : "file");
        }}
      />
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) setTarget(null);
        }}
        title={t(`settings.security.masterKey.${confirmKey}.title`)}
        description={t(`settings.security.masterKey.${confirmKey}.body`)}
        confirmLabel={t("settings.security.masterKey.confirmMove")}
        variant="default"
        pending={update.isPending}
        error={update.error}
        onConfirm={() => {
          if (target)
            update.mutate({ master_key_storage: target }, { onSuccess: () => setTarget(null) });
        }}
      />
    </SettingRow>
  );
}
