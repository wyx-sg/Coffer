// frontend/src/pages/sync/SyncRemoteTab.tsx — Sync › Remote (board 6.5.22).
//
// The one git repository this vault syncs with, as settings that save
// themselves like the rest of the app: a text field saves on blur (or Enter),
// a picker or switch the moment it moves. The remote is stored whole (one
// PUT), so every save sends the stored remote with that one field changed —
// never a half-typed draft, and never an invalid URL (that field says why and
// is not sent).
//
// "Run a round" also carries pause and resume: "Only when I press Sync now"
// stores `enabled: false` (see syncRemoteForm).
//
// `?focus=secret` — where the sign-in failure's "Choose secret" lands — opens
// the Secret picker.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type { SyncStatus } from "@/lib/api/sync";
import { useSaveSyncRemote } from "@/lib/hooks/useSync";
import { SyncRemoteFields } from "./SyncRemoteFields";
import { SyncStopSyncing } from "./SyncStopSyncing";
import { SyncVaultPath } from "./SyncVaultPath";
import {
  formFromRemote,
  toRemoteInput,
  validateRemote,
  type FormErrors,
  type FormState,
} from "./syncRemoteForm";

function sameInput(a: FormState, b: FormState, stored: SyncStatus["remote"]): boolean {
  return JSON.stringify(toRemoteInput(a, stored)) === JSON.stringify(toRemoteInput(b, stored));
}

export function SyncRemoteTab({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const save = useSaveSyncRemote();
  const [params] = useSearchParams();
  const stored = status.remote;

  // Keyed on the stored values, not the object a refetch hands back.
  const storedKey = JSON.stringify(stored);
  const savedForm = useMemo(
    () => formFromRemote(JSON.parse(storedKey) as SyncStatus["remote"]),
    [storedKey],
  );
  const [draft, setDraft] = useState<FormState>(savedForm);
  const [errors, setErrors] = useState<FormErrors>({});
  useEffect(() => setDraft(savedForm), [savedForm]);

  const onEdit = (patch: Partial<FormState>, commit: boolean) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    if (!commit) return;
    const found = validateRemote(next);
    setErrors(found);
    if (found.url || sameInput(next, savedForm, stored)) return;
    save.mutate(toRemoteInput(next, stored), {
      onSuccess: () => toast.success(t("common.saved")),
    });
  };

  return (
    <div className="flex max-w-[680px] flex-col gap-4" data-testid="sync-remote-tab">
      <Card className="flex flex-col gap-4 p-4">
        <SyncRemoteFields
          form={draft}
          onEdit={onEdit}
          errors={errors}
          busy={save.isPending}
          secrets={status.areas.secrets}
          confirmSecrets
          focusSecret={params.get("focus") === "secret"}
        />
        <SyncVaultPath path={status.vault_path} synchroniser={status.synchroniser} />
      </Card>
      <Card className="p-4">
        <SyncStopSyncing status={status} />
      </Card>
    </div>
  );
}
