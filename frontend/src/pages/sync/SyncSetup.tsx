// frontend/src/pages/sync/SyncSetup.tsx — the not-set-up / not-joined body
// (boards 6.4.20, 6.4.21, 6.4.22).
//
// First run is three steps, and nothing is stored until the repository has
// been looked at:
//
//   1. the form (6.4.20) — Repository URL, Branch, Secret, User name for an
//      HTTPS URL, Run a round, Include encrypted secrets — and Check
//      repository, asked of the draft;
//   2. an EMPTY repository (6.4.21) says what the first round pushes; Push
//      and start syncing stores the remote and joins it;
//   3. a repository that already holds a VAULT stores the remote at once and
//      shows the join preview (6.4.22), whose Back forgets it again.
//
// The page header carries the lead ("Keep this vault in step with a git
// repository you own…"); the body is sections and hairline rows, no card.
// Anything else the check finds is said under the form. A remote stored but
// not joined (set from the CLI, or a reload mid-setup) opens on the preview.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { SyncStatus } from "@/lib/api/sync";
import { useCheckRemote, useClearSyncRemote, useSaveSyncRemote } from "@/lib/hooks/useSync";
import { useJoin } from "@/lib/hooks/useSyncStop";
import { SyncEmptyRemote } from "./SyncEmptyRemote";
import { SyncJoinPreview } from "./SyncJoinPreview";
import { SyncRemoteCheck } from "./SyncRemoteCheck";
import { SyncRemoteFields } from "./SyncRemoteFields";
import {
  EMPTY_FORM,
  formFromRemote,
  toRemoteInput,
  validateRemote,
  type FormErrors,
  type FormState,
} from "./syncRemoteForm";

export function SyncSetup({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const check = useCheckRemote();
  const save = useSaveSyncRemote();
  const clear = useClearSyncRemote();
  const join = useJoin();
  const [draft, setDraft] = useState<FormState>(() => formFromRemote(status.remote));
  const [errors, setErrors] = useState<FormErrors>({});
  const [empty, setEmpty] = useState(false);

  const input = () => toRemoteInput(draft, null);

  if (empty) {
    return (
      <SyncEmptyRemote
        status={status}
        url={draft.url.trim()}
        includeSecret={draft.includeSecret}
        pending={save.isPending || join.isPending}
        onBack={() => setEmpty(false)}
        onPush={() => save.mutate(input(), { onSuccess: () => join.mutate() })}
      />
    );
  }

  if (status.configured && !status.joined) {
    return (
      <SyncJoinPreview
        backPending={clear.isPending}
        onBack={() => {
          setDraft(formFromRemote(status.remote));
          check.reset();
          // A refused DELETE leaves the preview where it is, so say why.
          clear.mutate(undefined, {
            onError: (error) => toast.error(translateApiError(t, error)),
          });
        }}
      />
    );
  }

  const busy = check.isPending || save.isPending;
  const runCheck = () => {
    const found = validateRemote(draft);
    setErrors(found);
    if (found.url) return;
    const body = input();
    check.mutate(
      { url: body.url, branch: body.branch, secret_ref: body.secret_ref, username: body.username },
      {
        onSuccess: (result) => {
          if (result.result === "empty") setEmpty(true);
          // A vault: store it; the status then says "configured, not joined"
          // and this body turns into the join preview.
          else if (result.result === "vault") save.mutate(body);
        },
      },
    );
  };

  return (
    <form
      className="flex flex-col gap-4"
      data-testid="sync-setup"
      onSubmit={(e) => {
        e.preventDefault();
        runCheck();
      }}
    >
      <SyncRemoteFields
        form={draft}
        onEdit={(patch) => setDraft((d) => ({ ...d, ...patch }))}
        errors={errors}
        busy={busy}
        secrets={status.areas.secrets}
        setup
      />
      <SyncRemoteCheck result={check.data} error={check.error} />
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={!draft.url.trim()} loading={busy}>
          {check.isPending ? t("sync.setup.checking") : t("sync.setup.checkRepo")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setDraft(EMPTY_FORM);
            setErrors({});
            check.reset();
          }}
        >
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}
