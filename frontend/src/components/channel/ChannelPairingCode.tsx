// frontend/src/components/channel/ChannelPairingCode.tsx
// Pairing, as the person does it: send a code to the bot from their own
// account, and wait. The code itself — large enough to read off one screen and
// type into another — with Copy, the platform's instruction, how long it stays
// valid, the one-tap link when the platform has one, and "Waiting for your
// message…" while the status poll watches for the pairing. A code past its
// expiry is struck through and says why. The buttons (New code, Done, Pair
// later…) belong to the dialog that hosts this; shared by the Add owner dialog
// and step 3 of Add channel.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, ExternalLink, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PairingCode } from "@/lib/api/channels";
import { botHandleOf, useNow } from "./pairingCode";
import { platformLabel } from "./PlatformMark";

/** "K7QM4XPT" → "K7QM 4XPT": easier to read aloud and to copy by eye. */
function spaced(code: string): string {
  return code.length === 8 ? `${code.slice(0, 4)} ${code.slice(4)}` : code;
}

interface Props {
  platform: string;
  /** The channel's name — what the person looks for in the platform's chat list. */
  channelName: string;
  code: PairingCode | undefined;
  expired: boolean;
  isPending: boolean;
  /** Offered only before a code exists (a refused request): issues the first. */
  onGenerate: () => void;
  /** Overrides the waiting line when it is somebody else who must send the code. */
  waitingText?: string;
}

export function ChannelPairingCode({
  platform,
  channelName,
  code,
  expired,
  isPending,
  onGenerate,
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

  const minutes = Math.ceil((new Date(code.expires_at).getTime() - now) / 60_000);
  const handle = botHandleOf(code);
  const copy = () => {
    void navigator.clipboard.writeText(code.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="flex flex-col gap-2.5" data-testid="channel-pairing-code">
      <div className="flex items-center gap-3 rounded-xl border border-border-subtle bg-surface-sidebar px-4 py-3.5">
        <span
          className={
            expired
              ? "font-mono text-[26px] font-medium tracking-[.12em] text-text-subtle line-through"
              : "font-mono text-[26px] font-medium tracking-[.12em] text-text"
          }
        >
          {spaced(code.code)}
        </span>
        <span className="ml-auto">
          {expired ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-warning">
              <span className="size-1.5 rounded-full bg-warning" aria-hidden />
              {t("channels.pairing.expired")}
            </span>
          ) : (
            <Button size="sm" variant="outline" onClick={copy}>
              <Copy aria-hidden />
              {copied ? t("channels.pairing.copied") : t("channels.pairing.copy")}
            </Button>
          )}
        </span>
      </div>
      {expired ? (
        <p className="text-sm leading-normal text-text-muted">
          {t("channels.pairing.expiredBody")}
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-1">
            <span className="text-sm text-text">
              {handle
                ? t("channels.pairing.instructionHandle", {
                    handle,
                    platform: platformLabel(platform),
                  })
                : t("channels.pairing.instruction", {
                    platform: platformLabel(platform),
                    name: channelName,
                  })}
            </span>
            <span className="text-xs text-text-subtle">
              {minutes <= 1
                ? t("channels.pairing.expiresSoon")
                : t("channels.pairing.expiresIn", { count: minutes })}
            </span>
          </div>
          {code.pair_url ? (
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
          <span
            className="inline-flex items-center gap-2 pt-1 text-sm text-text-muted"
            role="status"
          >
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            {waitingText ?? t("channels.pairing.waiting")}
          </span>
        </>
      )}
    </div>
  );
}
