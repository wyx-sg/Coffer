// frontend/src/pages/sync/SyncDeletionActions.tsx
//
// The two answers to a held round (spec vault-sync "Ask the user to confirm a
// tripped breaker"), as two buttons that each act at once: **Keep the files**
// restores them, **Delete N files** confirms the hold. There is no second
// dialog — the view above lists what a delete removes, and one line says what
// each answer does. A refusal shows in place; success goes back to Sync.
import { Trash2, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import type { SyncHold } from "@/lib/api/sync";
import { useConfirmHold, useRestoreHold } from "@/lib/hooks/useSyncStop";

interface Props {
  hold: SyncHold;
  /** Who deleted the files: the other Macs' names, or "this Mac". */
  who: string;
  onDone: () => void;
}

export function SyncDeletionActions({ hold, who, onDone }: Props) {
  const { t } = useTranslation();
  const confirm = useConfirmHold();
  const restore = useRestoreHold();
  const count = hold.paths.length;
  const busy = confirm.isPending || restore.isPending;
  const error = confirm.error ?? restore.error;

  return (
    <div className="flex flex-col gap-3" data-testid="sync-deletions-actions">
      <p className="text-xs text-text-muted">
        {t(`sync.deletions.hint.${hold.direction}`, { machine: who })}
      </p>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {translateApiError(t, error)}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          loading={restore.isPending}
          onClick={() => {
            confirm.reset();
            restore.mutate(undefined, { onSuccess: onDone });
          }}
        >
          <Undo2 aria-hidden />
          {t("sync.deletions.keep")}
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          disabled={busy}
          loading={confirm.isPending}
          onClick={() => {
            restore.reset();
            confirm.mutate(undefined, { onSuccess: onDone });
          }}
        >
          <Trash2 aria-hidden />
          {t("sync.deletions.delete", { count })}
        </Button>
      </div>
    </div>
  );
}
