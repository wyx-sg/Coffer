// frontend/src/pages/settings/SecuritySettings.tsx
//
// The Security settings tab. Controls where the master encryption key lives
// (file beside the DB vs. OS keychain). The card follows the same layout
// rhythm as DataSettings.tsx: explanation on the left, action on the right.
//
// Moving the key re-stores it and changes what the OS asks on every daemon
// start, so the switch confirms before it writes. Carrying the key to another
// machine is the Sync page's job, and the card links there rather than
// growing a second export/import surface.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import {
  useCredentialSettings,
  useUpdateCredentialSettings,
} from "@/lib/hooks/useCredentialSettings";

type Storage = "file" | "keychain";

export function SecuritySettings() {
  const { t } = useTranslation();
  const { data, isPending, error } = useCredentialSettings();
  const update = useUpdateCredentialSettings();
  // The storage the user asked to move to, while the confirmation is open.
  const [target, setTarget] = useState<Storage | null>(null);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-6">{t("common.loading")}</CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }

  const isKeychain = data!.master_key_storage === "keychain";
  const confirmKey = target === "keychain" ? "confirmKeychain" : "confirmFile";

  const move = () => {
    if (!target) return;
    update.mutate({ master_key_storage: target });
    setTarget(null);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.security.masterKey.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {t("settings.security.masterKey.description")}
        </p>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Label htmlFor="master-key-keychain">{t("settings.security.masterKey.toggle")}</Label>
            <p className="text-xs text-muted-foreground">
              {isKeychain
                ? t("settings.security.masterKey.keychainNote")
                : t("settings.security.masterKey.fileNote")}
            </p>
          </div>
          <Switch
            id="master-key-keychain"
            checked={isKeychain}
            disabled={update.isPending}
            onCheckedChange={(checked) => setTarget(checked ? "keychain" : "file")}
          />
        </div>

        <p className="text-sm">
          <Link to="/sync" className="text-primary hover:underline">
            {t("settings.security.masterKey.syncLink")}
          </Link>
        </p>

        {update.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {translateApiError(t, update.error)}
          </p>
        ) : null}

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
          onConfirm={move}
        />
      </CardContent>
    </Card>
  );
}
