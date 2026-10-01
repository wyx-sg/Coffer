// frontend/src/pages/sync/SyncPlaintextCard.tsx
//
// A round pushed nothing because a file it would publish holds a plaintext
// secret (spec vault-sync "Refuse to push a plaintext secret"). The card names
// each place — file, line, and the key the value is assigned to, never the
// value — and offers, like a rejected push: Retry, the agent hand-off that
// moves each value into a secret, and one more way out the detection needs,
// because it can be wrong: "Push anyway", confirmed first and audited.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeySquare, RotateCw, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SyncProblem } from "@/lib/api/sync";
import { usePushAnyway } from "@/lib/hooks/useSync";
import { SyncBannerCard } from "./SyncBanner";
import { Body, Handoff } from "./SyncProblemParts";

/** How many places the card lists; the hand-off and the CLI carry the rest. */
const MAX_PLACES = 8;

interface Props {
  problem: SyncProblem;
  onRun: () => void;
  running: boolean;
}

function Places({ problem }: { problem: SyncProblem }) {
  const { t } = useTranslation();
  const places = (problem.plaintext ?? []).filter((f) => f.current);
  return (
    <ul className="flex flex-col gap-1 text-sm" data-testid="sync-plaintext-places">
      {places.slice(0, MAX_PLACES).map((f) => (
        <li key={`${f.path}:${f.line}:${f.key}`} className="flex flex-wrap gap-x-2">
          <code className="rounded-xs bg-code px-1 py-0.5 font-mono text-xs text-text">
            {t("sync.problem.plaintext_found.where", { path: f.path, line: f.line })}
          </code>
          <span className="text-text-muted">
            {f.key === "token"
              ? t("sync.problem.plaintext_found.token")
              : t("sync.problem.plaintext_found.key", { key: f.key })}
          </span>
        </li>
      ))}
      {places.length > MAX_PLACES ? (
        <li className="text-text-subtle">+{places.length - MAX_PLACES}</li>
      ) : null}
    </ul>
  );
}

export function SyncPlaintextCard({ problem, onRun, running }: Props) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const push = usePushAnyway();
  return (
    <SyncBannerCard
      icon={KeySquare}
      tone="err"
      title={t("sync.problem.plaintext_found.title")}
      testId="sync-problem"
    >
      <Body>{t("sync.problem.plaintext_found.body")}</Body>
      <Places problem={problem} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onRun} loading={running}>
          <RotateCw aria-hidden />
          {t("sync.problem.retry")}
        </Button>
        <Handoff problem={problem} />
        <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
          <Upload aria-hidden />
          {t("sync.problem.plaintext_found.pushAnyway")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={(next) => {
          if (next) return;
          setConfirming(false);
          push.reset();
        }}
        title={t("sync.problem.plaintext_found.confirmTitle")}
        description={t("sync.problem.plaintext_found.confirmBody")}
        confirmLabel={t("sync.problem.plaintext_found.confirmLabel")}
        variant="destructive"
        pending={push.isPending}
        error={push.error}
        onConfirm={() => push.mutate(undefined, { onSuccess: () => setConfirming(false) })}
      />
    </SyncBannerCard>
  );
}
