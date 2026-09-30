// src/components/credentials/RevealSecretDialog.tsx — Reveal value, in the desktop app only.
//
// A warning first (anyone who can see the screen can read it; it shows for
// 30 seconds; the reveal is recorded in Activity), then the desktop app's
// presence check (Touch ID or the login password), then the value with Copy
// and Hide and a countdown. When the time runs out, or the dialog closes, the
// value is dropped (spec secret "Release plaintext only to a present
// human in the desktop app"). The menu never opens this in a browser.
import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import type { CredentialRef } from "@/lib/api/credentials";
import { translateApiError } from "@/lib/api/errors";
import { useRevealSecret } from "@/lib/hooks/useSecrets";
import { toneTextClass } from "@/lib/statusColors";
import { cn, formatDateTime } from "@/lib/utils";
import { displayName } from "./secretRows";
import { shortDate } from "./secretTimes";

/** How long a revealed value stays on screen. */
const REVEAL_SECONDS = 30;

interface Props {
  row: CredentialRef | null;
  onOpenChange: (open: boolean) => void;
}

export function RevealSecretDialog({ row, onOpenChange }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const reveal = useRevealSecret();
  const [left, setLeft] = useState(REVEAL_SECONDS);
  const [revealedAt, setRevealedAt] = useState<string | null>(null);
  const open = row !== null;
  const value = reveal.data;

  const { reset } = reveal;
  // Closing drops the value, whichever way the dialog closed.
  useEffect(() => {
    if (open) return;
    reset();
    setRevealedAt(null);
  }, [open, reset]);

  useEffect(() => {
    if (value === undefined) return;
    setLeft(REVEAL_SECONDS);
    const started = Date.now();
    const timer = setInterval(() => {
      const remaining = REVEAL_SECONDS - Math.floor((Date.now() - started) / 1000);
      if (remaining <= 0) {
        clearInterval(timer);
        onOpenChange(false);
      } else setLeft(remaining);
    }, 250);
    return () => clearInterval(timer);
  }, [value, onOpenChange]);

  if (!row) return null;
  const name = displayName(row);

  const start = () =>
    reveal.mutate(row.ref, { onSuccess: () => setRevealedAt(new Date().toISOString()) });
  const copy = () =>
    void navigator.clipboard
      .writeText(value ?? "")
      .then(() => toast.success(t("secrets.reveal.copied")))
      .catch(() => toast.error(t("secrets.menu.copyFailed")));

  return (
    <Dialog open={open} onOpenChange={(next) => !reveal.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        {value !== undefined ? (
          <>
            <DialogHeader>
              <DialogTitle className="font-mono">{name}</DialogTitle>
              <DialogDescription>
                {t("secrets.reveal.revealedAt", { time: formatDateTime(revealedAt ?? "") })}
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2">
              <code
                aria-label={t("secrets.reveal.valueLabel", { name })}
                className="min-w-0 flex-1 select-all break-all rounded-md border border-border-subtle bg-surface-sunken px-3 py-2 font-mono text-xs text-text"
              >
                {value}
              </code>
              <Button variant="outline" size="sm" onClick={copy}>
                {t("common.copy")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                {t("secrets.reveal.hide")}
              </Button>
            </div>
            <p className="text-xs text-text-muted" aria-live="polite">
              {t("secrets.reveal.hidesIn", { seconds: left })}
            </p>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>{t("common.done")}</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{t("secrets.reveal.title", { name })}</DialogTitle>
              <DialogDescription className="sr-only">
                {t("secrets.reveal.warningBody", { seconds: REVEAL_SECONDS })}
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-start gap-2.5 rounded-md border border-border-subtle bg-surface-sunken px-3 py-2.5">
              <AlertTriangle
                className={cn("mt-0.5 size-4 shrink-0", toneTextClass("warn"))}
                aria-hidden
              />
              <div className="space-y-0.5">
                <p className="text-sm font-semibold text-text">{t("secrets.reveal.warning")}</p>
                <p className="text-xs text-text-muted">
                  {t("secrets.reveal.warningBody", { seconds: REVEAL_SECONDS })}
                </p>
              </div>
            </div>
            <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
              <dt className="text-text-muted">{t("secrets.replace.secret")}</dt>
              <dd className="truncate font-mono text-text">{name}</dd>
              {row.created_at ? (
                <>
                  <dt className="text-text-muted">{t("secrets.cols.created")}</dt>
                  <dd className="text-text">{shortDate(row.created_at, i18n.language)}</dd>
                </>
              ) : null}
            </dl>
            {reveal.error ? (
              <p role="alert" className="text-xs text-danger">
                {translateApiError(t, reveal.error)}
              </p>
            ) : null}
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                {t("common.cancel")}
              </Button>
              <Button disabled={reveal.isPending} onClick={start}>
                {reveal.isPending
                  ? t("secrets.reveal.checking")
                  : t("secrets.reveal.submit", { seconds: REVEAL_SECONDS })}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
