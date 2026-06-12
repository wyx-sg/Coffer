// frontend/src/pages/settings/SecuritySettings.tsx
//
// The Security settings tab. Controls where the master encryption key lives
// (file beside the DB vs. OS keychain). The card follows the same layout
// rhythm as DataSettings.tsx and EmbeddingSettings.tsx: explanation on the
// left, action on the right.
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import {
  useCredentialSettings,
  useUpdateCredentialSettings,
} from "@/lib/hooks/useCredentialSettings";

export function SecuritySettings() {
  const { t } = useTranslation();
  const { data, isPending, error } = useCredentialSettings();
  const update = useUpdateCredentialSettings();

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
            onCheckedChange={(checked) => {
              update.mutate({ master_key_storage: checked ? "keychain" : "file" });
            }}
          />
        </div>

        {update.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {translateApiError(t, update.error)}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
