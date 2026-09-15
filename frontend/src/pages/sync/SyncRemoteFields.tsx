// frontend/src/pages/sync/SyncRemoteFields.tsx
//
// The remote's form fields: where it converges, on what branch, how often,
// which credential-store reference holds the push token, and whether
// credential ciphertext rides along.
//
// Presentational — it owns no state and saves nothing. The card above it keeps
// the draft, validates it, and persists it behind one Save button; this
// component only edits the draft and shows the field errors it is handed.
//
// There is deliberately no password field: the remote names its credential by
// reference, so a secret has no reason to exist in this component's tree.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { MIN_INTERVAL_SECONDS, type FormErrors, type FormState } from "./syncRemoteForm";

interface Props {
  form: FormState;
  setForm: (next: FormState) => void;
  errors: FormErrors;
  busy: boolean;
}

export function SyncRemoteFields({ form, setForm, errors, busy }: Props) {
  const { t } = useTranslation();

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="sync-url">{t("sync.remote.url")}</Label>
        <Input
          id="sync-url"
          value={form.url}
          disabled={busy}
          placeholder="https://git.example.com/me/coffer-vault.git"
          aria-invalid={errors.url ? true : undefined}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
        />
        {errors.url ? (
          <p className="text-xs text-destructive" role="alert">
            {t(`sync.remote.errors.${errors.url}`)}
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="min-w-0 flex-1 space-y-2">
          <Label htmlFor="sync-branch">{t("sync.remote.branch")}</Label>
          <Input
            id="sync-branch"
            value={form.branch}
            disabled={busy}
            onChange={(e) => setForm({ ...form, branch: e.target.value })}
          />
        </div>
        <div className="space-y-2 sm:w-48">
          <Label htmlFor="sync-interval">{t("sync.remote.interval")}</Label>
          <Input
            id="sync-interval"
            type="number"
            min={MIN_INTERVAL_SECONDS}
            value={form.intervalSeconds}
            disabled={busy}
            aria-invalid={errors.interval ? true : undefined}
            onChange={(e) =>
              setForm({ ...form, intervalSeconds: parseInt(e.target.value || "0", 10) || 0 })
            }
          />
          {errors.interval ? (
            <p className="text-xs text-destructive" role="alert">
              {t(`sync.remote.errors.${errors.interval}`)}
            </p>
          ) : null}
        </div>
      </div>

      {/* A name in the credential store, never the secret — see the module
          comment. There is deliberately no password field on this page. */}
      <div className="space-y-2">
        <Label htmlFor="sync-credential-ref">{t("sync.remote.credentialRef")}</Label>
        <Input
          id="sync-credential-ref"
          value={form.credentialRef}
          disabled={busy}
          placeholder="sync.PUSH_TOKEN"
          onChange={(e) => setForm({ ...form, credentialRef: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">{t("sync.remote.credentialRefHint")}</p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="sync-with-credentials">{t("sync.remote.includeCredentials")}</Label>
        <Switch
          id="sync-with-credentials"
          checked={form.includeCredentials}
          disabled={busy}
          onCheckedChange={(checked) => setForm({ ...form, includeCredentials: checked })}
        />
      </div>
      <p className="text-xs text-muted-foreground">{t("sync.remote.includeCredentialsHint")}</p>
    </>
  );
}
