// frontend/src/components/channel/ChannelFirstRun.tsx
// The Channels page before any channel exists: what a channel is for, and the
// platforms to choose from — a row opens Add channel at its Connect step for
// that platform. The page keeps its own header above this.
import { useTranslation } from "react-i18next";
import { Radio } from "lucide-react";

import type { ChannelType } from "@/lib/api/channels";
import { ChannelPlatformCards } from "./ChannelPlatformCards";

export function ChannelFirstRun({ onChoose }: { onChoose: (platform: ChannelType) => void }) {
  const { t } = useTranslation();
  return (
    <div
      className="mx-auto flex w-full max-w-[640px] flex-col gap-5 pt-12"
      data-testid="channels-first-run"
    >
      <div className="flex flex-col items-center gap-2.5 text-center">
        <span className="inline-flex size-10 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Radio className="size-5" aria-hidden />
        </span>
        <h2 className="text-md font-semibold text-text">{t("channels.firstRun.title")}</h2>
        <p className="max-w-[420px] text-sm leading-normal text-text-muted">
          {t("channels.firstRun.body")}
        </p>
      </div>
      <h3 className="text-sm font-semibold text-text">{t("channels.firstRun.choose")}</h3>
      <ChannelPlatformCards variant="list" onChoose={onChoose} />
    </div>
  );
}
