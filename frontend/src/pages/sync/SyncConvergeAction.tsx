// frontend/src/pages/sync/SyncConvergeAction.tsx — the "Converge now" button,
// and the join it may turn out to be (spec vault-sync "Report a join before
// applying it").
//
// A machine with no pointer does not run an ordinary round: its first round
// JOINS the remote, as new or as returning, and a join is explicit. So the
// button asks the daemon first (`GET /sync/join`, which applies nothing). A
// machine that already converged here runs its round at once; a joining one
// is shown which case it is, when it last converged, how many documents the
// remote changed since and how many this vault holds — and joins only from
// the dialog.
//
// The ambiguous case — a returning machine whose base is gone — has no safe
// default. The dialog names it and offers the one answer a browser can give,
// keeping this vault's documents; its confirm button says so in as many words.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { JoinPreview } from "@/lib/api/sync";
import { useAdoptRemote, usePreviewJoin, useRunConverge } from "@/lib/hooks/useSync";
import { SyncJoinReport } from "./SyncJoinReport";

export function SyncConvergeAction({
  disabled,
  joined = true,
}: {
  disabled: boolean;
  /** False until this machine adopts the remote: the button then offers the
   *  join by name. It still asks the daemon first either way. */
  joined?: boolean;
}) {
  const { t } = useTranslation();
  const run = useRunConverge();
  const preview = usePreviewJoin();
  const adopt = useAdoptRemote();
  const [join, setJoin] = useState<JoinPreview | null>(null);

  const busy = run.isPending || preview.isPending;
  const ambiguous = join?.case === "ambiguous";

  const start = () =>
    preview.mutate(undefined, {
      onSuccess: (answer) => (answer.joining ? setJoin(answer) : run.mutate()),
    });

  return (
    <>
      <Button type="button" variant="secondary" onClick={start} disabled={disabled || busy}>
        {busy
          ? t("sync.remote.converging")
          : joined
            ? t("sync.remote.convergeNow")
            : t("sync.join.action")}
      </Button>

      <ConfirmDialog
        open={join !== null}
        onOpenChange={(next) => {
          if (next) return;
          setJoin(null);
          // A refusal read once should not greet the next attempt.
          adopt.reset();
        }}
        title={t("sync.join.title")}
        description={t(`sync.join.case.${join?.case ?? "new"}`)}
        variant={ambiguous ? "destructive" : "default"}
        confirmLabel={
          adopt.isPending
            ? t("sync.join.joining")
            : ambiguous
              ? t("sync.join.keepLocal")
              : t("sync.join.confirm")
        }
        pending={adopt.isPending}
        error={adopt.error}
        onConfirm={() =>
          // Closes only on success, so a refused join stays up with its reason.
          adopt.mutate(ambiguous ? "keep-local" : undefined, { onSuccess: () => setJoin(null) })
        }
      >
        {join ? <SyncJoinReport report={join} /> : null}
      </ConfirmDialog>
    </>
  );
}
