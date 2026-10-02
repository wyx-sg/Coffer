// frontend/src/components/channel/ChannelPairingCode.tsx
// Pairing, as the person does it: generate a code, send it to the bot from
// their own account, and wait. Before a code exists this is the Generate
// button; once issued, the code itself — large enough to read off one screen
// and type into another — with Copy, how long it stays valid, the platform's
// one-tap link when it has one, and "Waiting for your message…" while the
// status poll watches for the pairing. A code past its expiry says so and
// offers a new one. Shared by the channel's Overview and the add dialog.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, ExternalLink, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PairingCode } from "@/lib/api/channels";
import { platformLabel } from "./PlatformMark";

/** Re-render every `ms` so a countdown moves while the panel is open. */
function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/** "K7QM4XPT" → "K7QM 4XPT": easier to read aloud and to copy by eye. */
function spaced(code: string): string {
  return code.length === 8 ? `${code.slice(0, 4)} ${code.slice(4)}` : code;
}

interface Props {
  platform: string;
  code: PairingCode | undefined;
  isPending: boolean;
  onGenerate: () => void;
  /** Withdraws the outstanding code. Offered only where the code is optional
   *  (adding an owner to a channel that already has one). */
  onCancel?: () => void;
  /** Overrides the waiting line when it is somebody else who must send the code. */
  waitingText?: string;
}

export function ChannelPairingCode({
  platform,
  code,
  isPending,
  onGenerate,
  onCancel,
  waitingText,
}: Props) {
  const { t } = useTranslation();
  const now = useNow(15_000);
  const [copied, setCopied] = useState(false);

  if (!code) {
    return (
      <Button size="sm" onClick={onGenerate} disabled={isPending}>
        {isPending ? t("channels.pairing.generating") : t("channels.pairing.generate")}
      </Button>
    );
  }

  const msLeft = new Date(code.expires_at).getTime() - now;
  const expired = msLeft <= 0;
  const minutes = Math.ceil(msLeft / 60_000);
  const copy = () => {
    void navigator.clipboard.writeText(code.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div
      className="flex flex-col gap-2.5 rounded-xl border border-border-subtle bg-surface-raised p-3.5"
      data-testid="channel-pairing-code"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={
            expired
              ? "font-mono text-xl font-semibold tracking-widest text-text-subtle line-through"
              : "font-mono text-xl font-semibold tracking-widest text-text"
          }
        >
          {spaced(code.code)}
        </span>
        {expired ? null : (
          <Button size="sm" variant="outline" onClick={copy}>
            <Copy aria-hidden />
            {copied ? t("channels.pairing.copied") : t("channels.pairing.copy")}
          </Button>
        )}
        <span className="text-xs text-text-muted">
          {expired
            ? t("channels.pairing.expired")
            : minutes <= 1
              ? t("channels.pairing.expiresSoon")
              : t("channels.pairing.expiresIn", { count: minutes })}
        </span>
      </div>
      <p className="text-xs leading-normal text-text-muted">
        {expired
          ? t("channels.pairing.expiredBody")
          : t("channels.pairing.instruction", { platform: platformLabel(platform) })}
      </p>
      {!expired && code.pair_url ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" asChild>
            <a href={code.pair_url} target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden />
              {t("channels.pairing.openIn", { platform: platformLabel(platform) })}
            </a>
          </Button>
          <span className="text-xs text-text-muted">{t("channels.pairing.openInHint")}</span>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {expired ? null : (
          <span className="inline-flex items-center gap-1.5 text-xs text-text-muted" role="status">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            {waitingText ?? t("channels.pairing.waiting")}
          </span>
        )}
        {onCancel ? (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onCancel}>
            {t("channels.pairing.cancel")}
          </Button>
        ) : null}
        <Button
          size="sm"
          variant={expired ? "default" : "ghost"}
          className={onCancel ? undefined : "ml-auto"}
          onClick={onGenerate}
          disabled={isPending}
        >
          <RefreshCw aria-hidden />
          {expired ? t("channels.pairing.newCodeAfterExpiry") : t("channels.pairing.newCode")}
        </Button>
      </div>
    </div>
  );
}
