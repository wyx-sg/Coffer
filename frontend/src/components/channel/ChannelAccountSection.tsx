// frontend/src/components/channel/ChannelAccountSection.tsx
// Who the channel answers, and how that changes: the paired account and the
// pairing code in one section, because pairing is not a separate subject — it
// is how the account gets there, and re-pairing is how it is replaced.
//
// Paired, the account's name is the headline and its ids and dates are quiet
// metadata under it; re-pairing is a secondary action, since it discards the
// current owner. Unpaired, the section is a call to act: one line saying what
// to do and the primary button that starts it. What pairing MEANS (the sender
// becomes the sole owner; re-pairing replaces it) is behind the heading's "?"
// in both states — worth knowing, not worth reading on every visit.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import type { ChannelStatus, PairingCode } from "@/lib/api/channels";
import { formatDateTime } from "@/lib/utils";

/** The issued code, large enough to read off one screen and type into another. */
function PairingCodePanel({ code }: { code: PairingCode }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(code.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="space-y-2 rounded-lg border border-primary/30 bg-accent-soft p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-display font-semibold tracking-[0.3em]">{code.code}</span>
        <Button size="sm" variant="outline" onClick={copy} aria-label={t("channels.pairing.copy")}>
          <Copy className="mr-1.5 size-3.5" />
          {copied ? t("channels.pairing.copied") : t("channels.pairing.copy")}
        </Button>
      </div>
      {code.pair_url ? (
        // "Pair by a one-tap start link": opening the link pairs in one tap; the code above
        // still works typed, for anyone reading it off another screen.
        <a
          href={code.pair_url}
          target="_blank"
          rel="noreferrer"
          className="block break-all text-xs text-primary underline"
        >
          {t("channels.pairing.openLink")}
        </a>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {t("channels.pairing.expires", { time: formatDateTime(code.expires_at) })}
      </p>
    </div>
  );
}

type ChannelPeer = NonNullable<ChannelStatus["peer"]>;

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt>{label}</dt>
      <dd className="text-foreground/80">{children}</dd>
    </div>
  );
}

export function ChannelAccountSection({
  peer,
  code,
  isPending,
  onGenerate,
}: {
  /** The paired account, or null before the first pairing. */
  peer: ChannelPeer | null;
  /** The code most recently issued from this page, if any. */
  code: PairingCode | undefined;
  isPending: boolean;
  onGenerate: () => void;
}) {
  const { t } = useTranslation();
  const paired = peer !== null;

  return (
    <section className="space-y-4" aria-labelledby="channel-account-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h2
            id="channel-account-heading"
            className="flex items-center gap-1 text-xs font-medium text-muted-foreground"
          >
            {t("channels.account.title")}
            <HelpTip label={t("channels.pairing.helpLabel")}>
              <p>{t("channels.pairing.instruction")}</p>
            </HelpTip>
          </h2>
          {paired ? (
            <>
              <p className="truncate text-base font-medium">{peer.display_name}</p>
              <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <Meta label={t("channels.status.chatId")}>
                  <code>{peer.chat_id}</code>
                </Meta>
                <Meta label={t("channels.status.pairedAt")}>{formatDateTime(peer.paired_at)}</Meta>
                <Meta label={t("channels.status.conversation")}>
                  {peer.active_conversation_id !== null ? (
                    <code>{peer.active_conversation_id}</code>
                  ) : (
                    t("channels.status.none")
                  )}
                </Meta>
              </dl>
            </>
          ) : (
            <>
              <p className="text-base font-medium text-muted-foreground">
                {t("channels.notPaired")}
              </p>
              <p className="text-xs text-muted-foreground">{t("channels.pairing.hint")}</p>
            </>
          )}
        </div>
        <Button
          size="sm"
          variant={paired ? "outline" : "default"}
          onClick={onGenerate}
          disabled={isPending}
        >
          {isPending
            ? t("channels.pairing.generating")
            : paired
              ? t("channels.pairing.repair")
              : t("channels.pairing.generate")}
        </Button>
      </div>
      {code ? <PairingCodePanel code={code} /> : null}
    </section>
  );
}
