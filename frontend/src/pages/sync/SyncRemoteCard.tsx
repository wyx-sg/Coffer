// frontend/src/pages/sync/SyncRemoteCard.tsx — Sync → Status → Remote
// (spec vault-sync). The one git repository this vault converges with: enable
// it, name the repository and branch, say how often, say whether credential
// ciphertext rides along, and run a round now.
//
// Every edit auto-saves, so there is no Save button — the shape every other
// configuration surface in Coffer uses.
//
// Nothing here ever holds the push credential. The form's credential field is
// a *reference* — a name in Coffer's credential store — which the daemon
// resolves at push time and nowhere else; that is why this card can render a
// fully configured remote in a browser with nothing to redact.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SyncStatus } from "@/lib/api/sync";
import { useRunConverge, useSaveSyncRemote } from "@/lib/hooks/useSync";
import { SyncRemoteFields, type FormState } from "./SyncRemoteFields";

/** The spec's defaults, so an unconfigured card opens on them rather than blank. */
const DEFAULT_BRANCH = "main";
const DEFAULT_INTERVAL_SECONDS = 3600;

export function SyncRemoteCard({ status }: { status: SyncStatus | null }) {
  const { t } = useTranslation();
  const save = useSaveSyncRemote();
  const run = useRunConverge();

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

  /**
   * Persist the whole remote. A blank URL is not a configuration the daemon
   * will take, so an empty form simply does not save — the user is still
   * typing their repository in.
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sync.remote.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.remote.description")}</p>

        <SyncRemoteFields
          form={form}
          setForm={setForm}
          busy={busy}
          commit={commit}
          blurOnEnter={blurOnEnter}
          toggle={toggle}
        />

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => run.mutate()}
            disabled={busy || run.isPending || !saved}
          >
            {run.isPending ? t("sync.remote.converging") : t("sync.remote.convergeNow")}
          </Button>
          {worktreePath ? (
            <span className="text-xs text-muted-foreground">
              {t("sync.remote.worktree", { path: worktreePath })}
            </span>
          ) : null}
        </div>

        {!saved ? (
          <p className="text-xs text-muted-foreground">{t("sync.remote.notConfigured")}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
