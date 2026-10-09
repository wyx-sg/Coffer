// frontend/src/components/channel/AddChannelDialog.tsx
// Add channel, in three steps — 1 Platform · 2 Connect · 3 Pair. Choosing a
// platform (here, or on the first-run page, which opens the dialog straight
// at step 2) leads to the form; Connect registers the channel (secrets first,
// rolled back on failure — registerChannel.ts); Pair issues a code and waits
// for the owner's message. Closing after the channel exists opens it.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
import type { ChannelType } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { channelPlatform } from "@/lib/channels/channelState";
import { channelPath } from "@/lib/channels/tabs";
import { AddChannelConnectStep } from "./AddChannelConnectStep";
import { AddChannelPairStep } from "./AddChannelPairStep";
import type { AddStep } from "./addChannel";
import { AddChannelPlatformStep, AddChannelStepper } from "./AddChannelSteps";
import { platformLabel } from "./PlatformMark";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Open at step 2 for this platform (a first-run card was chosen). */
  initialPlatform?: ChannelType | null;
}

export function AddChannelDialog({ open, onOpenChange, initialPlatform = null }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [step, setStep] = useState<AddStep>("platform");
  const [platform, setPlatform] = useState<ChannelType | null>(null);
  const [created, setCreated] = useState<ResourceOut | null>(null);

  useEffect(() => {
    if (!open) return;
    setPlatform(initialPlatform);
    setStep(initialPlatform ? "connect" : "platform");
    setCreated(null);
  }, [open, initialPlatform]);

  const close = () => {
    onOpenChange(false);
    if (created) navigate(channelPath(created.uid));
  };

  const title =
    step === "pair" && created
      ? t("channels.add.pairTitle", {
          platform: platformLabel(channelPlatform(created.config)),
          name: created.name,
        })
      : step === "connect" && platform
        ? t("channels.add.connectTitle", { platform: platformLabel(platform) })
        : t("channels.add.title");

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent className="max-w-[640px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription asChild>
            <div>
              <AddChannelStepper step={step} />
            </div>
          </DialogDescription>
        </DialogHeader>
        {step === "platform" ? (
          <>
            <AddChannelPlatformStep selected={platform} onSelect={setPlatform} />
            <DialogFooter>
              <Button variant="ghost" onClick={close}>
                {t("common.cancel")}
              </Button>
              <Button disabled={platform === null} onClick={() => setStep("connect")}>
                {t("channels.add.next")}
              </Button>
            </DialogFooter>
          </>
        ) : step === "connect" && platform ? (
          <AddChannelConnectStep
            platform={platform}
            onBack={() => setStep("platform")}
            onCancel={close}
            onCreated={(channel) => {
              toast.success(t("channels.dialog.created", { name: channel.name }));
              setCreated(channel);
              setStep("pair");
            }}
          />
        ) : created ? (
          <AddChannelPairStep channel={created} onDone={close} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
