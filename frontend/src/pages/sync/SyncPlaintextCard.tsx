// frontend/src/pages/sync/SyncPlaintextCard.tsx
//
// A round pushed nothing because a file it would publish holds a plaintext
// secret (spec vault-sync "Refuse to push a plaintext secret"). The card names
// each place — file, line, and the key the value is assigned to, never the
// value — and offers the way out: "Move into secrets…" opens the Secrets scan
// limited to those files, and one more way out the detection needs, because
// it can be wrong: "Push anyway…", confirmed first and audited.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeySquare, Upload } from "lucide-react";

import { ScanSecretsDialog } from "@/components/secret/ScanSecretsDialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SyncProblem } from "@/lib/api/sync";
import { usePushAnyway } from "@/lib/hooks/useSync";
import { SyncBannerCard } from "./SyncBanner";
import { Actions, Body } from "./SyncProblemParts";

/** How many places the card lists; the scan dialog carries the rest. */
const MAX_PLACES = 8;

interface Props {
  problem: SyncProblem;
  onIgnore?: () => void;
}

function Places({ places }: { places: NonNullable<SyncProblem["plaintext"]> }) {
  const { t } = useTranslation();
  return (
    <ul
      className="mt-1 flex flex-col gap-1 rounded-md border border-border-subtle bg-surface-raised/70 px-2.5 py-2 text-xs"
      data-testid="sync-plaintext-places"
    >
      {places.slice(0, MAX_PLACES).map((f) => (
        <li key={`${f.path}:${f.line}:${f.key}`} className="flex flex-wrap gap-x-2">
          <code className="font-mono text-xs text-text-muted">
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

export function SyncPlaintextCard({ problem, onIgnore }: Props) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const [moving, setMoving] = useState(false);
  const push = usePushAnyway();
  const places = (problem.plaintext ?? []).filter((f) => f.current);
  const files = [...new Set(places.map((f) => f.path))];
  return (
    <SyncBannerCard
      icon={KeySquare}
      tone="err"
      title={t("sync.problem.plaintext_found.title", { count: files.length })}
      onIgnore={onIgnore}
      testId="sync-problem"
    >
      <Body>{t("sync.problem.plaintext_found.body")}</Body>
      <Places places={places} />
      <Actions>
        <Button type="button" variant="outline" size="sm" onClick={() => setMoving(true)}>
          {t("sync.problem.plaintext_found.move")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
          <Upload aria-hidden />
          {t("sync.problem.plaintext_found.pushAnyway")}
        </Button>
      </Actions>
      <ScanSecretsDialog open={moving} onOpenChange={setMoving} onlyPaths={files} />
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
