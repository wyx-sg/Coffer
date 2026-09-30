// frontend/src/components/channel/ChannelFirstRun.tsx
// The Channels page before any channel exists: what a channel is for, the
// platforms to choose from (a card opens Add channel at its Connect step for
// that platform), and three short lines on what you get.
import { useTranslation } from "react-i18next";
import { Lock, MessageSquare, Users } from "lucide-react";

import type { ChannelType } from "@/lib/api/channels";
import { ChannelPlatformCards } from "./ChannelPlatformCards";
import { PLATFORMS } from "./channelPlatforms";

const BENEFITS = [
  { key: "chat", icon: MessageSquare },
  { key: "onlyYou", icon: Lock },
  { key: "groups", icon: Users },
] as const;

export function ChannelFirstRun({ onChoose }: { onChoose: (platform: ChannelType) => void }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-6" data-testid="channels-first-run">
      <div className="space-y-1.5">
        <h2 className="text-lg font-bold">{t("channels.firstRun.title")}</h2>
        <p className="max-w-measure text-sm leading-normal text-text-muted">
          {t("channels.firstRun.body")}
        </p>
      </div>
      <section className="space-y-2.5" aria-label={t("channels.firstRun.choose")}>
        <h3 className="flex items-center text-xs font-semibold text-text-muted">
          {t("channels.firstRun.choose")}
          <span className="ml-auto font-book">
            {t("channels.platforms.count", { count: PLATFORMS.length })}
          </span>
        </h3>
        <ChannelPlatformCards onChoose={onChoose} />
      </section>
      <ul className="grid gap-4 sm:grid-cols-3">
        {BENEFITS.map(({ key, icon: Icon }) => (
          <li key={key} className="flex gap-2.5">
            <Icon className="mt-0.5 size-4 shrink-0 text-text-muted" aria-hidden />
            <span className="space-y-0.5">
              <span className="block text-sm font-label">
                {t(`channels.firstRun.benefits.${key}.title`)}
              </span>
              <span className="block text-xs leading-normal text-text-muted">
                {t(`channels.firstRun.benefits.${key}.body`)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
