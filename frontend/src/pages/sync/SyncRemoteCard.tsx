// frontend/src/pages/sync/SyncRemoteCard.tsx — Sync → Status → Remote
// (spec vault-sync). The one git repository this vault converges with: name
// the repository and branch, say how often, say whether credential
// ciphertext rides along, save it, and run a round now — or, on a machine that
// has not joined yet, see what joining would do and join (SyncConvergeAction).
//
// An explicit form rather than field-by-field auto-save: a half-typed URL is
// not a remote the daemon should be handed, so the draft is checked
// client-side and Save stays disabled until it is both changed and valid.
// The one exception is "Converge automatically", which flips the stored
// remote on and off the moment it moves — and only once a remote is stored,
// because before that there is nothing for it to switch.
//
// Nothing here ever holds the push credential. The form's credential field is
// a *reference* — a name in Coffer's credential store — which the daemon
// resolves at push time and nowhere else; that is why this card can render a
// fully configured remote in a browser with nothing to redact.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import type { SyncStatus } from "@/lib/api/sync";
import { useSaveSyncRemote } from "@/lib/hooks/useSync";
import { SyncConvergeAction } from "./SyncConvergeAction";
import { SyncJoinReport } from "./SyncJoinReport";
import { SyncRemoteFields } from "./SyncRemoteFields";
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
  const savedIncludeCredentials = saved?.include_credentials ?? false;
  const savedInterval = saved?.interval_seconds ?? DEFAULT_INTERVAL_SECONDS;
  const savedEnabled = saved?.enabled ?? true;
  const worktreePath = saved?.worktree_path ?? null;

  const savedForm = useMemo<FormState>(
    () => ({
      url: savedUrl,
      branch: savedBranch,
      credentialRef: savedCredentialRef,
      includeCredentials: savedIncludeCredentials,
      intervalSeconds: savedInterval,
    }),
    [savedUrl, savedBranch, savedCredentialRef, savedIncludeCredentials, savedInterval],
  );
  const [form, setForm] = useState<FormState>(savedForm);

  // Re-sync once the daemon's answer lands (and after every save round-trip);
  // without this the form keeps whatever the first render saw.
  useEffect(() => setForm(savedForm), [savedForm]);

  const busy = save.isPending;
  const errors = validateRemote(form);
  const dirty = isDirty(form, savedForm);
  // Field errors only once the user has changed something — an untouched
  // empty form is not a mistake yet.
  const shownErrors = dirty ? errors : {};
  const canSave = dirty && !errors.url && !errors.interval && !busy;

  /**
   * Persist the whole remote. `worktree_path` rides along unchanged when the
   * daemon already has one: this card does not offer it, and omitting it
   * would silently reset an adopted working tree to the default. A remote
   * saved for the first time starts enabled — the switch takes over after.
   */
  const persist = (next: FormState, enabled: boolean) =>
    save.mutate(
      {
        url: next.url.trim(),
        branch: next.branch.trim() || DEFAULT_BRANCH,
        credential_ref: next.credentialRef.trim() || null,
        include_credentials: next.includeCredentials,
        interval_seconds: next.intervalSeconds,
        enabled,
        ...(worktreePath ? { worktree_path: worktreePath } : {}),
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
          <SyncRemoteFields form={form} setForm={setForm} errors={shownErrors} busy={busy} />

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!canSave}>
              {busy ? t("common.saving") : t("sync.remote.save")}
            </Button>
            <SyncConvergeAction
              disabled={busy || !saved}
              joined={!saved || status?.joined !== false}
            />
            {worktreePath ? (
              <span className="text-xs text-muted-foreground">
                {t("sync.remote.worktree", { path: worktreePath })}
              </span>
            ) : null}
          </div>
        </form>

        {!saved ? (
          <p className="text-xs text-muted-foreground">{t("sync.remote.notConfigured")}</p>
        ) : null}
        {saved && status?.joined === false ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{t("sync.join.notJoined")}</p>
            {/* What the last round detected, before anyone joins. */}
            {status.last_run?.join_report ? (
              <>
                <p className="text-sm">
                  {t(`sync.join.detected.${status.last_run.join_report.case ?? "new"}`)}
                </p>
                <SyncJoinReport report={status.last_run.join_report} />
              </>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
