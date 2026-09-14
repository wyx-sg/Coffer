// frontend/src/pages/sync/SyncRemoteFields.tsx
//
// The remote's form fields: where it converges, on what branch, how often,
// which credential-store reference holds the push token, and whether
// credential ciphertext rides along.
//
// Presentational — it owns no state and saves nothing. The card above it keeps
// the draft and decides when to persist, which is what lets every field here
// follow the same auto-save rule (commit on blur or Enter) without repeating
// it six times.
//
// There is deliberately no password field: the remote names its credential by
// reference, so a secret has no reason to exist in this component's tree.
import type React from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export interface FormState {
  url: string;
  branch: string;
  credentialRef: string;
  includeCredentials: boolean;
  intervalSeconds: number;
  enabled: boolean;
}

interface Props {
  form: FormState;
  setForm: (next: FormState) => void;
  busy: boolean;
  commit: () => void;
  blurOnEnter: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  toggle: (field: "enabled" | "includeCredentials") => (checked: boolean) => void;
}

export function SyncRemoteFields({ form, setForm, busy, commit, blurOnEnter, toggle }: Props) {
  const { t } = useTranslation();

  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="sync-enabled">{t("sync.remote.enabled")}</Label>
        <Switch
          id="sync-enabled"
          checked={form.enabled}
          disabled={busy}
          onCheckedChange={toggle("enabled")}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="sync-url">{t("sync.remote.url")}</Label>
        <Input
          id="sync-url"
          value={form.url}
          disabled={busy}
          placeholder="https://git.example.com/me/coffer-vault.git"
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          onBlur={commit}
          onKeyDown={blurOnEnter}
        />
      </div>

      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="min-w-0 flex-1 space-y-2">
          <Label htmlFor="sync-branch">{t("sync.remote.branch")}</Label>
          <Input
            id="sync-branch"
            value={form.branch}
            disabled={busy}
            onChange={(e) => setForm({ ...form, branch: e.target.value })}
            onBlur={commit}
            onKeyDown={blurOnEnter}
          />
        </div>
        <div className="space-y-2 sm:w-48">
          <Label htmlFor="sync-interval">{t("sync.remote.interval")}</Label>
          <Input
            id="sync-interval"
            type="number"
            min={1}
            value={form.intervalSeconds}
            disabled={busy}
            onChange={(e) =>
              setForm({
                ...form,
                intervalSeconds: Math.max(1, parseInt(e.target.value || "0", 10) || 1),
              })
            }
            onBlur={commit}
            onKeyDown={blurOnEnter}
          />
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
          onBlur={commit}
          onKeyDown={blurOnEnter}
        />
        <p className="text-xs text-muted-foreground">{t("sync.remote.credentialRefHint")}</p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="sync-with-credentials">{t("sync.remote.includeCredentials")}</Label>
        <Switch
          id="sync-with-credentials"
          checked={form.includeCredentials}
          disabled={busy}
          onCheckedChange={toggle("includeCredentials")}
        />
      </div>
      <p className="text-xs text-muted-foreground">{t("sync.remote.includeCredentialsHint")}</p>
    </>
  );
}
