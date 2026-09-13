// frontend/src/pages/sync/SyncLastRoundCard.tsx
//
// What the last converge round actually did, read straight off
// `GET /sync/status` (spec vault-sync `## The converge round`).
//
// Purely presentational — it fetches nothing and decides nothing. Two of the
// lists here are reported even on a round that went perfectly, on purpose:
// `agent_resolved`, because a silent machine merge of the user's own notes is
// precisely what they would want to know about, and `locked_refs`, because a
// machine holding ciphertext without the key must say so rather than fail
// decryption quietly.
//
// The error text arrives already scrubbed of any push token by the daemon;
// nothing here needs to redact, and nothing here should start.
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConvergeRound, DiffCounts } from "@/lib/api/sync";
import { SyncRoundPathList } from "./SyncRoundPathList";

function Counts({ labelKey, counts }: { labelKey: string; counts: DiffCounts }) {
  const { t } = useTranslation();
  return (
    <p className="text-sm">
      <span className="text-muted-foreground">{t(labelKey)}: </span>
      {t("sync.round.counts", { ...counts })}
    </p>
  );
}

export function SyncLastRoundCard({ round }: { round: ConvergeRound | null }) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sync.round.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3" data-testid="sync-last-round">
        {!round ? (
          <p className="text-sm text-muted-foreground">{t("sync.round.none")}</p>
        ) : (
          <>
            <p className="text-sm" role="status">
              {t("sync.round.status", {
                status: t(`sync.round.statusLabel.${round.status}`, round.status),
              })}
            </p>
            {round.join ? (
              <p className="text-sm text-muted-foreground">{t(`sync.round.join.${round.join}`)}</p>
            ) : null}

            <Counts labelKey="sync.round.applied" counts={round.applied} />
            <Counts labelKey="sync.round.published" counts={round.published} />

            {round.commit ? (
              <p className="text-xs text-muted-foreground">
                {t("sync.round.commit", { commit: round.commit })}
              </p>
            ) : null}

            <SyncRoundPathList
              titleKey="sync.round.agentResolved"
              hintKey="sync.round.agentResolvedHint"
              items={round.agent_resolved}
              testId="sync-agent-resolved"
            />
            <SyncRoundPathList
              titleKey="sync.round.failures"
              items={round.failures.map((f) =>
                t("sync.round.failure", { path: f.path, reason: f.reason }),
              )}
              tone="err"
              testId="sync-round-failures"
            />
            <SyncRoundPathList
              titleKey="sync.round.lockedRefs"
              hintKey="sync.round.lockedRefsHint"
              items={round.locked_refs}
              tone="warn"
              testId="sync-locked-refs"
            />

            {round.error ? (
              <p className="text-xs text-destructive" role="alert">
                {round.error}
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
