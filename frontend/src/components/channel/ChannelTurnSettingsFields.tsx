// frontend/src/components/channel/ChannelTurnSettingsFields.tsx
// The parts of a channel's Settings that shape its turns, in the two places
// the tab shows them: `ChannelBatchingFields` — when it answers in a group and
// how long it waits for a burst of messages to end — near the top, and
// `ChannelReplyDirectoryFields` — how a running turn shows itself (the
// completion ping, the step lines) and its working directories — after the
// machine. Switches and list edits save at once; typed values save a moment
// after typing stops, and only when valid (useSettingDraft).
//
// Every starting value is read from the daemon's typed settings
// (`ChannelSettings`, defaults filled in), never from the raw config.
import { useState } from "react";

import type { ChannelSettings } from "@/lib/api/channels";
import { parseBurstWait, parseIdleHours, parseNotifyAfter } from "./channelTurnSettings";
import {
  honoursRequireMention,
  normaliseDirectory,
  storedDefaultDirectory,
  type ChannelEditValues,
} from "@/lib/channels/editChannel";
import { EditChannelBurstFields } from "./EditChannelBurstFields";
import { EditChannelDirectoriesField } from "./EditChannelDirectoriesField";
import { EditChannelGroupFields, type ChannelGroupDraft } from "./EditChannelGroupFields";
import { EditChannelIdleField } from "./EditChannelIdleField";
import { EditChannelReplyFields } from "./EditChannelReplyFields";
import { useSettingDraft } from "./useSettingDraft";

type Save = (values: Partial<ChannelEditValues>) => void;

/** A typed default folder: blank clears it, an absolute path sets it, anything
 *  else is invalid (`null`) and is not saved. */
const parseDefault = (text: string): { path: string | null } | null => {
  if (text.trim() === "") return { path: null };
  const path = normaliseDirectory(text);
  return path === null ? null : { path };
};

export function ChannelBatchingFields({
  settings,
  save,
}: {
  settings: ChannelSettings;
  save: Save;
}) {
  const channelType = settings.channel_type;

  const [group, setGroup] = useState<ChannelGroupDraft>(() => ({
    requireMention: settings.require_mention,
    ignoreOtherMentions: settings.ignore_other_mentions,
  }));
  const afterText = useSettingDraft(String(settings.wait_after_text_seconds), parseBurstWait, (v) =>
    save({ wait_after_text_seconds: v }),
  );
  const afterForward = useSettingDraft(
    String(settings.wait_after_forward_seconds),
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
  settings,
  save,
}: {
  settings: ChannelSettings;
  save: Save;
}) {
  const [showSteps, setShowSteps] = useState(() => settings.show_steps);
  const [directories, setDirectories] = useState(() => settings.directories);
  const notifyAfter = useSettingDraft(
    String(settings.notify_after_seconds),
    parseNotifyAfter,
    (v) => save({ notify_after_seconds: v }),
  );
  const idle = useSettingDraft(
    String(settings.new_conversation_after_idle_hours),
    parseIdleHours,
    (v) => save({ new_conversation_after_idle_hours: v }),
  );
  const defaultDir = useSettingDraft(storedDefaultDirectory(settings) ?? "", parseDefault, (v) =>
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
      <div onBlur={idle.flush}>
        <EditChannelIdleField value={idle.text} onChange={idle.change} />
      </div>
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
