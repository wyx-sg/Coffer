// frontend/src/components/channel/AddChannelPairStep.tsx
// Step 3 of Add channel, once the channel exists: a pairing code is issued as
// the step opens, shown with Copy, its expiry and (Telegram) the one-tap
// link, and the channel's status is polled until someone pairs — then the
// step turns into the done state: who, that nobody else is answered, and how
// to try it. "Pair later" leaves the code outstanding; the channel's Overview
// can issue another any time.
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import type { PairingCode } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { useAgents } from "@/lib/hooks/useAgents";
import { useIssuePairingCode } from "@/lib/hooks/useChannelPairing";
import { useChannelStatus } from "@/lib/hooks/useChannels";
import { channelPlatform } from "@/lib/channels/channelState";
import { ChannelPairingCode } from "./ChannelPairingCode";
import { botHandleOf, usePairingExpired } from "./pairingCode";

interface Props {
  channel: ResourceOut;
  onDone: () => void;
}

export function AddChannelPairStep({ channel, onDone }: Props) {
  const { t } = useTranslation();
  const pairing = useIssuePairingCode(channel.uid);
  const { data: status } = useChannelStatus(channel.uid, { poll: true });
  const { data: agents } = useAgents();
  const issued = useRef(false);
  const platform = channelPlatform(channel.config);
  const peer = status?.people[0] ?? null;
  // The code is kept in this step's own state, not read off the mutation: the
  // step issues it as it opens, and under StrictMode's mount-unmount-mount the
  // mutation's observer is dropped before the answer lands — its `data` would
  // never arrive and the step would read "Generating…" for good.
  const [code, setCode] = useState<PairingCode | undefined>(undefined);
  const [issuing, setIssuing] = useState(false);
  const expired = usePairingExpired(code);
  const { mutateAsync } = pairing;
  const issue = useCallback(() => {
    setIssuing(true);
    // A refusal is toasted by the hook; the step then offers Generate again.
    mutateAsync()
      .then(setCode, () => undefined)
      .finally(() => setIssuing(false));
  }, [mutateAsync]);

  useEffect(() => {
    if (issued.current) return;
    issued.current = true;
    issue();
  }, [issue]);

  if (peer) {
    const agentUid = channel.config.default_agent;
    const agent = agents?.find((a) => a.uid === agentUid);
    const bot = botHandleOf(code);
    return (
      <div className="space-y-3.5" data-testid="channel-paired">
        <div className="flex gap-2.5 rounded-lg bg-success-soft px-3.5 py-3">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          <div className="space-y-0.5">
            <p className="text-sm font-label text-text">
              {t("channels.add.paired.title", { owner: peer.display_name })}
            </p>
            <p className="text-xs leading-normal text-text-muted">
              {t("channels.add.paired.body", { name: channel.name })}
            </p>
          </div>
        </div>
        <p className="text-sm text-text-muted">
          {t("channels.add.paired.tryIt", {
            bot: bot ? `@${bot}` : channel.name,
            agent: agent ? agent.name : t("channels.add.paired.yourAgent"),
          })}
        </p>
        <DialogFooter>
          <Button onClick={onDone}>{t("common.done")}</Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <div className="space-y-3.5">
      <ChannelPairingCode
        platform={platform}
        channelName={channel.name}
        code={code}
        expired={expired}
        isPending={issuing}
        onGenerate={issue}
      />
      {expired ? (
        <Button size="sm" onClick={issue} disabled={issuing}>
          {t("channels.pairing.newCodeAfterExpiry")}
        </Button>
      ) : null}
      <DialogFooter>
        <Button variant="ghost" onClick={onDone}>
          {t("channels.add.pairLater")}
        </Button>
      </DialogFooter>
    </div>
  );
}
