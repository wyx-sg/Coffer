// src/components/channel/ChannelCommands.tsx — every command a channel answers, on its Overview.
//
// The roster comes from the daemon with the channel's status (the one list that
// also feeds /help and the platform's own command menu), so this page can never
// disagree with what the bot does. Each row is the word with its argument hint
// and one line in the UI's language. A command that needs the Knowledge feature
// is listed only while that feature is on.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { ChannelStatus } from "@/lib/api/channels";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";

export function ChannelCommands({ commands }: { commands: ChannelStatus["commands"] | undefined }) {
  const { t, i18n } = useTranslation();
  const knowledge = useFeatureEnabled("knowledge") === true;
  const zh = i18n.language.startsWith("zh");
  const shown = (commands ?? []).filter((c) => !c.needs_knowledge || knowledge);
  if (shown.length === 0) return null;
  return (
    <Section
      title={t("channels.overview.commands.title")}
      help={t("channels.overview.commands.help")}
      labelled
    >
      <ul className="flex flex-col" data-testid="channel-commands">
        {shown.map((c) => (
          <li
            key={c.name}
            className="grid grid-cols-[minmax(8rem,12rem)_minmax(0,1fr)] items-baseline gap-3 border-t border-border-subtle py-1.5 first:border-t-0"
          >
            <code className="truncate font-mono text-xs text-text">
              {`/${c.name}${c.args ? ` ${c.args}` : ""}`}
            </code>
            <span className="text-sm text-text-muted">{zh ? c.description_zh : c.description}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}
