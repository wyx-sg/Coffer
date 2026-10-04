// frontend/src/pages/sync/SyncPlaintextCard.tsx
//
// A round pushed nothing because a file it would publish holds a plaintext
// secret (spec vault-sync "Refuse to push a plaintext secret"). The card names
// each place — file, line, and the key the value is assigned to, never the
// value — each opening to its masked lines so the person can judge it (spec
// vault-sync "Show a plaintext finding in its file") — and offers two ways out:
// "Move into secrets…", the Secrets page's move scoped to the flagged files,
// after which the person syncs again; and "Push anyway…", which the detection
// needs because it can be wrong, confirmed first and audited. There is no
// agent hand-off: a secret is never handed to an agent.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeySquare, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ScanSecretsDialog } from "@/components/secret/ScanSecretsDialog";
import type { SyncProblem } from "@/lib/api/sync";
import { usePushAnyway } from "@/lib/hooks/useSync";
import { SyncBannerCard } from "./SyncBanner";
import { PlaintextPlace } from "./SyncPlaintextPlace";
import { Actions, Body } from "./SyncProblemParts";

/** How many places the card lists; the rest are counted. */
const MAX_PLACES = 8;

interface Props {
  problem: SyncProblem;
  onIgnore?: () => void;
}

function Places({ places }: { places: NonNullable<SyncProblem["plaintext"]> }) {
  return (
    <ul
      className="mt-1 flex flex-col gap-1 rounded-md border border-border-subtle bg-surface-raised/70 px-2.5 py-2 text-xs"
      data-testid="sync-plaintext-places"
    >
      {places.slice(0, MAX_PLACES).map((f) => (
        <PlaintextPlace key={`${f.path}:${f.line}:${f.key}`} finding={f} />
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
          {t("sync.problem.plaintext_found.moveIntoSecrets")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
          <Upload aria-hidden />
          {t("sync.problem.plaintext_found.pushAnyway")}
        </Button>
      </Actions>
      <ScanSecretsDialog open={moving} onOpenChange={setMoving} only={files} />
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
