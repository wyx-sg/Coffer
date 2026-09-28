// frontend/src/components/channel/ChannelOverviewCard.tsx
// Everything the channel detail page operates, in one card (spec channels,
// "Manage channels from the Channels page and the CLI"): a status strip (is
// it live, and where), the account (who it answers, and pairing), and test
// delivery (does a message actually arrive). Three sections of one card rather
// than four cards, because they are read top to bottom as one checklist — live?
// paired? delivering? — and separate cards gave each the same visual weight
// whether it had anything to say or not.
//
// The card owns the pairing and notify mutations so the page stays the frame:
// header, edit and delete.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ChannelStatus } from "@/lib/api/channels";
import { useIssuePairingCode, useNotifyChannel } from "@/lib/hooks/useChannels";
import { ChannelAccountSection } from "./ChannelAccountSection";
import { ChannelStatusStrip } from "./ChannelStatusStrip";

/**
 * One row, one button: push a fixed message to the paired account through the
 * notify capability — the live check for a freshly paired channel. The text is
 * fixed because the question is "does delivery work", which any message
 * answers; a free-text box asked the reader to compose something first.
 * Disabled until there is an account to deliver to.
 */
function TestDeliveryRow({ uid, hasPeer }: { uid: string; hasPeer: boolean }) {
  const { t } = useTranslation();
  const notify = useNotifyChannel(uid);

  return (
    <section className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0 space-y-0.5">
        <h2 className="text-xs font-medium text-muted-foreground">{t("channels.test.title")}</h2>
        <p className="text-sm">
          {hasPeer ? t("channels.test.subtitle") : t("channels.test.needsPeer")}
        </p>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => notify.mutate(t("channels.test.fixedMessage"))}
        disabled={!hasPeer || notify.isPending}
      >
        {notify.isPending ? t("channels.test.sending") : t("channels.test.send")}
      </Button>
    </section>
  );
}

export function ChannelOverviewCard({
  uid,
  name,
  config,
  status,
}: {
  uid: string;
  name: string;
  config: Record<string, unknown>;
  status: ChannelStatus | undefined;
}) {
  const { t } = useTranslation();
  const pairing = useIssuePairingCode(uid);

  return (
    <Card className="paper-card divide-y" data-testid="channel-overview-card">
      <div className="p-5">
        {status === undefined ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : (
          <ChannelStatusStrip uid={uid} name={name} config={config} status={status} />
        )}
      </div>
      <div className="p-5">
        <ChannelAccountSection
          peer={status?.peer ?? null}
          code={pairing.data}
          isPending={pairing.isPending}
          onGenerate={() => pairing.mutate()}
        />
      </div>
      <div className="p-5">
        <TestDeliveryRow uid={uid} hasPeer={status?.peer != null} />
      </div>
    </Card>
  );
}
