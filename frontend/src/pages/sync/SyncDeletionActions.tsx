// frontend/src/pages/sync/SyncDeletionActions.tsx
//
// The foot of Review held deletions (spec vault-sync "Ask the user to confirm
// a tripped breaker"): one line saying what each answer does, Leave for later,
// and the two answers as two buttons that each act at once — **Keep the
// files** restores them, **Delete N files** confirms the hold. There is no
// second dialog: the page above shows each file a delete removes. A refusal
// shows in place; success goes back to Sync.
import { Trash2, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

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
    <>
      <p className="max-w-prose text-xs text-text-muted" data-testid="sync-deletions-hint">
        {t(`sync.deletions.hint.${hold.direction}`, { machine: who })}
      </p>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {translateApiError(t, error)}
        </p>
      ) : null}
      <div className="ml-auto flex items-center gap-2" data-testid="sync-deletions-actions">
        <Button asChild variant="ghost">
          <Link to="/sync">{t("sync.resolve.later")}</Link>
        </Button>
        <Button
          type="button"
          variant="outline"
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
    </>
  );
}
