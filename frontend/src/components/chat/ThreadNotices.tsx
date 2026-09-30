// src/components/chat/ThreadNotices.tsx — the two notices that take the place of
// (or sit above) an open conversation's composer: an archived conversation is
// read-only until restored, and a live stream lost mid-turn after every
// reconnect says so and offers to reload what the turn has written so far.
import { useTranslation } from "react-i18next";
import { WifiOff } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ArchivedNotice({
  onRestore,
  pending,
}: {
  onRestore?: () => void;
  pending?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between gap-3 border-t border-border-subtle bg-surface-raised px-5 py-3">
      <span className="text-sm text-text-muted">{t("conversations.archivedThread.notice")}</span>
      <Button size="sm" onClick={onRestore} disabled={pending || !onRestore}>
        {pending
          ? t("conversations.archivedThread.restoring")
          : t("conversations.archivedThread.restore")}
      </Button>
    </div>
  );
}

export function StreamLostBanner({ onReload }: { onReload?: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="mx-auto mb-2 flex w-full max-w-[720px] items-start gap-3 rounded-xl border border-border bg-surface-raised px-4 py-3"
    >
      <WifiOff className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-semibold text-text">{t("conversations.streamLost.title")}</p>
        <p className="text-xs text-text-muted">{t("conversations.streamLost.body")}</p>
      </div>
      {onReload ? (
        <Button variant="outline" size="sm" onClick={onReload}>
          {t("conversations.streamLost.reload")}
        </Button>
      ) : null}
    </div>
  );
}
