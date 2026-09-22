// src/components/SyncAttentionBanner.tsx — floating banner when the vault's last
// converge round is waiting on a human (spec vault-sync FR-096).
import { useTranslation } from "react-i18next";
import { Link, useMatch } from "react-router-dom";
import { AlertTriangle, PauseCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { RoundStatus } from "@/lib/api/sync";
import { useSyncStatus } from "@/lib/hooks/useSync";

/**
 * The round statuses that mean the user has something to do — the same set the
 * CLI exits non-zero on (`_NEEDS_ATTENTION` in `surfaces/cli/sync_cmd.py`).
 * Kept as one list rather than four call sites so a status added there is
 * added here too, and not silently carried by one surface only.
 */
const NEEDS_ATTENTION: readonly RoundStatus[] = [
  "conflict",
  "awaiting_confirmation",
  "push_failed",
  "failed",
];

/**
 * Shown above every page but `/sync` while the last round needs answering.
 *
 * Why it is global and not a card on `/sync`. The first hold in the field stood
 * for four days: the guard held a publish-side round, the only surface that
 * said so was the page the user had no reason to open, and the vault stopped
 * converging AND stopped backing up in silence. A held vault converges no
 * further, so a hold nobody sees is an outage that looks like nothing at all —
 * hence a banner on whatever page the user is already on.
 *
 * `awaiting_confirmation` reads differently from the rest on purpose. A
 * conflict or a failed push still leaves rounds running (and the next one may
 * clear it by itself); a hold stops everything until the user answers, and
 * only the user can answer it.
 *
 * No Confirm/Reject here, deliberately. Answering a hold means reading which
 * direction it was raised in, which areas breached and which paths would go —
 * none of which fits a one-line banner, and all of which the `/sync` row
 * already carries. The banner's whole job is to get the user there — which is
 * also why it stands down on `/sync` itself: the user has arrived, and a
 * floating banner would sit over the very row that answers it.
 *
 * Silence is the default everywhere else: no remote, no round yet, or a round
 * that ended fine renders nothing. A query error renders nothing either — a
 * daemon that cannot answer has DaemonOfflineBanner (which floats in the same
 * place) and the same recovery, and stale cached data must not outlive it into
 * a second banner stacked on the first.
 */
export function SyncAttentionBanner() {
  const { t } = useTranslation();
  // The sync page is a flat route; its tabs are query params, so one match
  // covers it.
  const onSyncPage = useMatch("/sync") !== null;
  const { data: status, isError } = useSyncStatus();

  const round = status?.last_run ?? null;
  if (onSyncPage) return null;
  // `enabled` is load-bearing, not belt and braces. A disabled remote makes
  // `run_once` return a DISABLED round WITHOUT recording it, so `last_run`
  // keeps whatever it last was — and a user who answers a hold by switching
  // sync off rather than by answering it would otherwise be told about that
  // hold on every page, for ever, with no way to clear it but to turn sync
  // back on.
  if (isError || !status?.configured || !status.remote?.enabled || !round) return null;
  if (!NEEDS_ATTENTION.includes(round.status)) return null;

  const held = round.status === "awaiting_confirmation";
  // Literal keys, one per status: `src/i18n/locales.test.ts` can only check the
  // `t("…")` form, and this copy is the whole point of the banner.
  const body = held
    ? t("sync.attention.heldBody")
    : round.status === "conflict"
      ? t("sync.attention.conflictBody")
      : round.status === "push_failed"
        ? t("sync.attention.pushFailedBody")
        : t("sync.attention.failedBody");

  // Same floating treatment as DaemonOfflineBanner: fixed and top-centered, so
  // it never shifts page content, and pointer-events pass through the gutter.
  return (
    <Alert
      variant="warning"
      className="pointer-events-auto w-full max-w-xl shadow-lg"
      data-testid="sync-attention-banner"
      data-round-status={round.status}
    >
      {held ? (
        <PauseCircle className="size-4" aria-hidden />
      ) : (
        <AlertTriangle className="size-4" aria-hidden />
      )}
      <AlertTitle className="font-serif text-base">
        {held ? t("sync.attention.heldTitle") : t("sync.attention.title")}
      </AlertTitle>
      <AlertDescription>
        <p className="mb-3 text-foreground/80">{body}</p>
        <Button asChild size="sm" variant="outline">
          <Link to="/sync">{t("sync.attention.open")}</Link>
        </Button>
      </AlertDescription>
    </Alert>
  );
}
