// frontend/src/pages/sync/SyncRemoteCard.tsx — Sync → Setup → Remote
// (spec vault-sync). The one git repository this vault syncs with: name the
// repository and branch, say how often, say whether the encrypted secrets ride
// along, check what the repository holds, save it — and pause, resume or stop.
//
// An explicit form rather than field-by-field auto-save: a half-typed URL is
// not a remote the daemon should be handed, so Save stays disabled until the
// draft is both changed and valid. The one exception is the pause switch,
// which flips the STORED remote the moment it moves — and only once a remote
// is stored, because before that there is nothing for it to switch.
//
// Nothing here ever holds the push credential: the field is a REFERENCE — a
// name in Coffer's credential store — which the daemon resolves at push time
// and nowhere else, so a configured remote renders with nothing to redact.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import type { SyncStatus } from "@/lib/api/sync";
import { useSaveSyncRemote } from "@/lib/hooks/useSync";
import { SyncRemoteCheck } from "./SyncRemoteCheck";
import { SyncRemoteFields } from "./SyncRemoteFields";
import { SyncStopSyncing } from "./SyncStopSyncing";
import { SyncVaultPath } from "./SyncVaultPath";
import {
  DEFAULT_BRANCH,
  DEFAULT_INTERVAL_SECONDS,
  isDirty,
  validateRemote,
  type FormState,
} from "./syncRemoteForm";

export function SyncRemoteCard({ status }: { status: SyncStatus | null }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const save = useSaveSyncRemote();

  const saved = status?.remote ?? null;
  // Primitive-by-primitive, so re-syncing the form depends on the values
  // rather than on the identity of the object a refetch happens to hand back.
  const savedUrl = saved?.url ?? "";
  const savedBranch = saved?.branch ?? DEFAULT_BRANCH;
  const savedCredentialRef = saved?.credential_ref ?? "";
  const savedIncludeSecret = saved?.include_secret ?? false;
  const savedInterval = saved?.interval_seconds ?? DEFAULT_INTERVAL_SECONDS;
  const savedEnabled = saved?.enabled ?? true;

  const savedForm = useMemo<FormState>(
    () => ({
      url: savedUrl,
      branch: savedBranch,
      credentialRef: savedCredentialRef,
      includeSecret: savedIncludeSecret,
      intervalSeconds: savedInterval,
    }),
    [savedUrl, savedBranch, savedCredentialRef, savedIncludeSecret, savedInterval],
  );
  const [form, setForm] = useState<FormState>(savedForm);
  // Re-sync once the daemon's answer lands (and after every save round-trip).
  useEffect(() => setForm(savedForm), [savedForm]);

  const busy = save.isPending;
  const errors = validateRemote(form);
  const dirty = isDirty(form, savedForm);
  // Field errors only once the user has changed something.
  const shownErrors = dirty ? errors : {};
  const canSave = dirty && !errors.url && !errors.interval && !busy;

  /** Persist the whole remote. A remote saved for the first time starts
   *  enabled — the pause switch takes over after. */
  const persist = (next: FormState, enabled: boolean) =>
    save.mutate(
      {
        url: next.url.trim(),
        branch: next.branch.trim() || DEFAULT_BRANCH,
        credential_ref: next.credentialRef.trim() || null,
        // Not on this form (set with `coffer sync remote set --username`): kept.
        ...(saved?.username ? { username: saved.username } : {}),
        include_secret: next.includeSecret,
        interval_seconds: next.intervalSeconds,
        enabled,
      },
      { onSuccess: () => toast.success(t("common.saved")) },
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sync.remote.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.remote.description")}</p>
        {status ? (
          <SyncVaultPath path={status.vault_path} synchroniser={status.synchroniser} />
        ) : null}

        <div className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="sync-enabled">{t("sync.remote.enabled")}</Label>
            {!saved ? (
              <p className="text-xs text-muted-foreground">{t("sync.remote.enabledHint")}</p>
            ) : null}
          </div>
          {/* Flips the STORED remote, never the draft: unsaved edits stay
              unsaved, and the switch is inert until there is a remote. */}
          <Switch
            id="sync-enabled"
            checked={saved ? savedEnabled : false}
            disabled={busy || !saved}
            onCheckedChange={(checked) => persist(savedForm, checked)}
          />
        </div>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSave) persist(form, savedEnabled);
          }}
        >
          <SyncRemoteFields
            form={form}
            secrets={status?.areas.secrets ?? 0}
            setForm={setForm}
            errors={shownErrors}
            busy={busy}
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!canSave}>
              {busy ? t("common.saving") : t("sync.remote.save")}
            </Button>
            <SyncRemoteCheck form={form} disabled={busy || Boolean(errors.url)} />
            {saved ? <SyncStopSyncing disabled={busy} /> : null}
          </div>
        </form>

        {!saved ? (
          <p className="text-xs text-muted-foreground">{t("sync.remote.notConfigured")}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
