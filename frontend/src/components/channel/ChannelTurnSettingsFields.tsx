// frontend/src/components/channel/ChannelTurnSettingsFields.tsx
// The parts of a channel's Settings that shape its turns, in the two places
// the tab shows them: `ChannelBatchingFields` — when it answers in a group and
// how long it waits for a burst of messages to end — near the top, and
// `ChannelReplyDirectoryFields` — how a running turn shows itself (the
// completion ping, the step lines) and its working directories — after the
// machine. Switches and list edits save at once; typed values save a moment
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
  honoursRequireMention,
  normaliseDirectory,
  storedDefaultDirectory,
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

/** A typed default folder: blank clears it, an absolute path sets it, anything
 *  else is invalid (`null`) and is not saved. */
const parseDefault = (text: string): { path: string | null } | null => {
  if (text.trim() === "") return { path: null };
  const path = normaliseDirectory(text);
  return path === null ? null : { path };
};

export function ChannelBatchingFields({ channel, save }: { channel: ResourceOut; save: Save }) {
  const config = channel.config;
  const channelType = typeof config.channel_type === "string" ? config.channel_type : "telegram";

  const [group, setGroup] = useState<ChannelGroupDraft>(() => ({
    requireMention: boolField(config, "require_mention", true),
    ignoreOtherMentions: boolField(config, "ignore_other_mentions", false),
  }));
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
    </>
  );
}

export function ChannelReplyDirectoryFields({
  channel,
  save,
}: {
  channel: ResourceOut;
  save: Save;
}) {
  const config = channel.config;
  const [showSteps, setShowSteps] = useState(() => storedShowSteps(config));
  const [directories, setDirectories] = useState(() => storedDirectories(config));
  const notifyAfter = useSettingDraft(String(storedNotifyAfter(config)), parseNotifyAfter, (v) =>
    save({ notify_after_seconds: v }),
  );
  const defaultDir = useSettingDraft(storedDefaultDirectory(config) ?? "", parseDefault, (v) =>
    save({ default_directory: v.path }),
  );

  return (
    <>
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
      <div onBlur={defaultDir.flush}>
        <EditChannelDirectoriesField
          defaultText={defaultDir.text}
          onDefaultChange={defaultDir.change}
          directories={directories}
          onDirectoriesChange={(next) => {
            setDirectories(next);
            save({ directories: next });
          }}
        />
      </div>
    </>
  );
}
