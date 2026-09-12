// frontend/src/pages/settings/SyncBackupCard.tsx
//
// Settings → Sync → Backup (spec vault-export-import `## Backup`). The one git
// remote this vault pushes its exports to: enable it, name the repository and
// branch, say how often, say whether credential ciphertext rides along, and
// read what the last run did. Shaped like the retention-policy card — every
// edit auto-saves, so there is no Save button, matching every other settings
// surface.
//
// Two queries on purpose: `GET /sync/remote` is the configuration this form
// edits, and `GET /sync/status` carries the last run, which the form never
// writes. "Back up now" posts to `/sync/push` and both refresh.
//
// Nothing here ever holds the push credential. The form's credential field is
// a *reference* — a name in Coffer's credential store — which the daemon
// resolves at push time and nowhere else; that is why this card can render a
// fully configured backup in a browser with nothing to redact.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import {
  useBackupRemote,
  useBackupStatus,
  useRunBackupNow,
  useSaveBackupRemote,
} from "@/lib/hooks/useSync";
import { SyncBackupLastRun } from "./SyncBackupLastRun";
import { SyncBackupFields, type FormState } from "./SyncBackupFields";

/** The spec's defaults, so an unconfigured card opens on them rather than blank. */
const DEFAULT_BRANCH = "main";
const DEFAULT_INTERVAL_SECONDS = 3600;


export function SyncBackupCard() {
  const { t } = useTranslation();
  const remoteQuery = useBackupRemote();
  const statusQuery = useBackupStatus();
  const save = useSaveBackupRemote();
  const runNow = useRunBackupNow();

  const saved = remoteQuery.data?.remote ?? null;
  // Primitive-by-primitive, so re-syncing the form depends on the values
  // rather than on the identity of the object a refetch happens to hand back.
  const savedUrl = saved?.url ?? "";
  const savedBranch = saved?.branch ?? DEFAULT_BRANCH;
  const savedCredentialRef = saved?.credential_ref ?? "";
  const savedIncludeCredentials = saved?.include_credentials ?? false;
  const savedInterval = saved?.interval_seconds ?? DEFAULT_INTERVAL_SECONDS;
  const savedEnabled = saved?.enabled ?? true;
  const worktreePath = saved?.worktree_path ?? null;

  const [form, setForm] = useState<FormState>({
    url: savedUrl,
    branch: savedBranch,
    credentialRef: savedCredentialRef,
    includeCredentials: savedIncludeCredentials,
    intervalSeconds: savedInterval,
    enabled: savedEnabled,
  });

  // Re-sync once the daemon's answer lands (and after every auto-save
  // round-trip); without this the form keeps whatever the first render saw.
  useEffect(() => {
    setForm({
      url: savedUrl,
      branch: savedBranch,
      credentialRef: savedCredentialRef,
      includeCredentials: savedIncludeCredentials,
      intervalSeconds: savedInterval,
      enabled: savedEnabled,
    });
  }, [
    savedUrl,
    savedBranch,
    savedCredentialRef,
    savedIncludeCredentials,
    savedInterval,
    savedEnabled,
  ]);

  const busy = save.isPending;
  const lastRun = statusQuery.data?.last_run ?? null;

  /**
   * Persist the whole remote. A blank URL is not a configuration the daemon
   * will take (it raises BACKUP_REMOTE_INVALID), so an empty form simply does
   * not save — the user is still typing their repository in.
   *
   * `worktree_path` rides along unchanged when the daemon already has one:
   * this card does not offer it, and omitting it would silently reset an
   * adopted working tree to the default.
   */
  const persist = (next: FormState) => {
    if (!next.url.trim()) return;
    save.mutate({
      url: next.url.trim(),
      branch: next.branch.trim() || DEFAULT_BRANCH,
      credential_ref: next.credentialRef.trim() || null,
      include_credentials: next.includeCredentials,
      interval_seconds: next.intervalSeconds,
      enabled: next.enabled,
      ...(worktreePath ? { worktree_path: worktreePath } : {}),
    });
  };

  // Switches persist the moment they move; text and number fields persist when
  // the user finishes with them (blur or Enter), and only when the value
  // actually differs — no write per keystroke, no round-trip on a no-op blur.
  const toggle = (field: "enabled" | "includeCredentials") => (checked: boolean) => {
    const next = { ...form, [field]: checked };
    setForm(next);
    persist(next);
  };

  const commit = () => {
    const changed =
      form.url.trim() !== savedUrl ||
      form.branch.trim() !== savedBranch ||
      form.credentialRef.trim() !== savedCredentialRef ||
      form.intervalSeconds !== savedInterval;
    if (changed) persist(form);
  };

  const blurOnEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };

  const error = remoteQuery.error ?? save.error ?? runNow.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.backup.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-foreground/70">{t("settings.sync.backup.description")}</p>

        <SyncBackupFields
          form={form}
          setForm={setForm}
          busy={busy}
          commit={commit}
          blurOnEnter={blurOnEnter}
          toggle={toggle}
        />

        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="backup-with-credentials">
            {t("settings.sync.backup.includeCredentials")}
          </Label>
          <Switch
            id="backup-with-credentials"
            checked={form.includeCredentials}
            disabled={busy}
            onCheckedChange={toggle("includeCredentials")}
          />
        </div>
        <p className="text-xs text-foreground/60">
          {t("settings.sync.backup.includeCredentialsHint")}
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => runNow.mutate()}
            disabled={busy || runNow.isPending || !saved}
          >
            {runNow.isPending
              ? t("settings.sync.backup.pushing")
              : t("settings.sync.backup.pushNow")}
          </Button>
          {worktreePath && (
            <span className="text-xs text-foreground/60">
              {t("settings.sync.backup.worktree", { path: worktreePath })}
            </span>
          )}
        </div>

        <SyncBackupLastRun lastRun={lastRun} />

        {error && (
          <p className="text-xs text-destructive" role="alert">
            {translateApiError(t, error)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
