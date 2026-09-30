// frontend/src/components/channel/ChannelTurnSettingsFields.tsx
// The half of a channel's Settings that shapes its turns: when it answers in
// a group, how long it waits for a burst of messages to end, how a running
// turn shows itself (the step list, the completion ping), and the folders
// /dir may switch into. Switches save at once; typed values save a moment
// after typing stops, and only when valid (useSettingDraft).
import { useState } from "react";

import type { ResourceOut } from "@/lib/api/resources";
import {
  parseBurstWait,
  parseNotifyAfter,
  storedBurstWait,
  storedNotifyAfter,
  storedShowSteps,
} from "./channelTurnSettings";
import {
  directoriesDraftValid,
  honoursRequireMention,
  parseDirectories,
  storedDirectories,
  type ChannelEditValues,
} from "./editChannel";
import { EditChannelBurstFields } from "./EditChannelBurstFields";
import { EditChannelDirectoriesField } from "./EditChannelDirectoriesField";
import { EditChannelGroupFields, type ChannelGroupDraft } from "./EditChannelGroupFields";
import { EditChannelReplyFields } from "./EditChannelReplyFields";
import { useSettingDraft } from "./useSettingDraft";

type Save = (values: Partial<ChannelEditValues>) => void;

function boolField(config: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const v = config[key];
  return typeof v === "boolean" ? v : fallback;
}

const parseDirs = (text: string) =>
  directoriesDraftValid(text) ? parseDirectories(text).directories : null;

export function ChannelTurnSettingsFields({ channel, save }: { channel: ResourceOut; save: Save }) {
  const config = channel.config;
  const channelType = typeof config.channel_type === "string" ? config.channel_type : "telegram";

  const [group, setGroup] = useState<ChannelGroupDraft>(() => ({
    requireMention: boolField(config, "require_mention", true),
    ignoreOtherMentions: boolField(config, "ignore_other_mentions", false),
  }));
  const [showSteps, setShowSteps] = useState(() => storedShowSteps(config));

  const afterText = useSettingDraft(
    String(storedBurstWait(config, "wait_after_text_seconds")),
    parseBurstWait,
    (v) => save({ wait_after_text_seconds: v }),
  );
  const afterForward = useSettingDraft(
    String(storedBurstWait(config, "wait_after_forward_seconds")),
    parseBurstWait,
    (v) => save({ wait_after_forward_seconds: v }),
  );
  const notifyAfter = useSettingDraft(String(storedNotifyAfter(config)), parseNotifyAfter, (v) =>
    save({ notify_after_seconds: v }),
  );
  const dirs = useSettingDraft(storedDirectories(config).join("\n"), parseDirs, (v) =>
    save({ directories: v }),
  );

  return (
    <>
      <EditChannelGroupFields
        channelType={channelType}
        draft={group}
        onChange={(patch) => {
          const next = { ...group, ...patch };
          setGroup(next);
          save({
            require_mention: honoursRequireMention(channelType) ? next.requireMention : undefined,
            ignore_other_mentions: next.ignoreOtherMentions,
          });
        }}
      />
      <EditChannelBurstFields
        draft={{ waitAfterText: afterText.text, waitAfterForward: afterForward.text }}
        onChange={(patch) => {
          if (patch.waitAfterText !== undefined) afterText.change(patch.waitAfterText);
          if (patch.waitAfterForward !== undefined) afterForward.change(patch.waitAfterForward);
        }}
      />
      <EditChannelReplyFields
        draft={{ showSteps, notifyAfter: notifyAfter.text }}
        onChange={(patch) => {
          if (patch.showSteps !== undefined) {
            setShowSteps(patch.showSteps);
            save({ show_steps: patch.showSteps });
          }
          if (patch.notifyAfter !== undefined) notifyAfter.change(patch.notifyAfter);
        }}
      />
      <EditChannelDirectoriesField value={dirs.text} onChange={dirs.change} />
    </>
  );
}
