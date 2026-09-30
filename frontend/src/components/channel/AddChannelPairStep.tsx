// frontend/src/components/channel/AddChannelPairStep.tsx
// Step 3 of Add channel, once the channel exists: a pairing code is issued as
// the step opens, shown with Copy, its expiry and (Telegram) the one-tap
// link, and the channel's status is polled until someone pairs — then the
// step says who, and that nobody else will be answered. "Pair later" leaves
// the code outstanding; the channel's Overview can issue another any time.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import type { ResourceOut } from "@/lib/api/resources";
import { useChannelStatus, useIssuePairingCode } from "@/lib/hooks/useChannels";
import { displayName } from "@/lib/resourceTitle";
import { channelPlatform } from "./channelState";
import { ChannelPairingCode } from "./ChannelPairingCode";

interface Props {
  channel: ResourceOut;
  onDone: () => void;
}

export function AddChannelPairStep({ channel, onDone }: Props) {
  const { t } = useTranslation();
  const pairing = useIssuePairingCode(channel.uid);
  const { data: status } = useChannelStatus(channel.uid, { poll: true });
  const issued = useRef(false);
  const platform = channelPlatform(channel.config);
  const peer = status?.peer ?? null;

  useEffect(() => {
    if (issued.current) return;
    issued.current = true;
    pairing.mutate();
  }, [pairing]);

  if (peer) {
    return (
      <div className="space-y-4" data-testid="channel-paired">
        <div className="flex gap-2.5 rounded-xl bg-success-soft p-3.5">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          <div className="space-y-1">
            <p className="text-sm font-label text-text">
              {t("channels.add.paired.title", { owner: peer.display_name })}
            </p>
            <p className="text-xs leading-normal text-text-muted">
              {t("channels.add.paired.body", { name: displayName(channel) })}
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={onDone}>{t("common.done")}</Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ChannelPairingCode
        platform={platform}
        code={pairing.data}
        isPending={pairing.isPending}
        onGenerate={() => pairing.mutate()}
      />
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          {t("channels.add.pairLater")}
        </Button>
      </DialogFooter>
    </div>
  );
}
