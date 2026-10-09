// frontend/src/components/channel/ChannelTurnSettingsFields.tsx
// The rows of a channel's Settings that shape its turns, one export per section
// the tab draws (the tab owns the section cards; these are rows only):
// `ChannelReceivingFields` — when it answers in a group and how long it waits
// for a burst of messages to end; `ChannelReplyFields` — how a running turn shows
// itself (the step lines, where the platform has a live status line) and when a
// chat starts a fresh conversation; `ChannelDirectoryFields` — its working directories. Switches and
// list edits save at once; typed values save a moment after typing stops, and
// only when valid (useSettingDraft).
//
// Every starting value is read from the daemon's typed settings
// (`ChannelSettings`, defaults filled in), never from the raw config.
import { useState } from "react";

import type { ChannelSettings } from "@/lib/api/channels";
import { parseBurstWait, parseIdleHours } from "./channelTurnSettings";
import {
  honoursRequireMention,
  showsStepLines,
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

export function ChannelReceivingFields({
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

export function ChannelReplyFields({ settings, save }: { settings: ChannelSettings; save: Save }) {
  const [showSteps, setShowSteps] = useState(() => settings.show_steps);
  const idle = useSettingDraft(
    String(settings.new_conversation_after_idle_hours),
    parseIdleHours,
    (v) => save({ new_conversation_after_idle_hours: v }),
  );

  return (
    <>
      {showsStepLines(settings.channel_type) && (
        <EditChannelReplyFields
          showSteps={showSteps}
          onChange={(next) => {
            setShowSteps(next);
            save({ show_steps: next });
          }}
        />
      )}
      <div onBlur={idle.flush}>
        <EditChannelIdleField value={idle.text} onChange={idle.change} />
      </div>
    </>
  );
}

export function ChannelDirectoryFields({
  settings,
  workspaceDirectory,
  save,
}: {
  settings: ChannelSettings;
  workspaceDirectory: string;
  save: Save;
}) {
  // A default the list does not hold yet (set before the two were one list) is
  // shown in it, and joins it with the next change.
  const stored = storedDefaultDirectory(settings);
  const [dirs, setDirs] = useState(() => ({
    directories:
      stored && !settings.directories.includes(stored)
        ? [...settings.directories, stored]
        : settings.directories,
    defaultDirectory: stored,
  }));

  return (
    <EditChannelDirectoriesField
      directories={dirs.directories}
      defaultDirectory={dirs.defaultDirectory}
      workspaceDirectory={workspaceDirectory}
      onChange={(directories, defaultDirectory) => {
        setDirs({ directories, defaultDirectory });
        save({ directories, default_directory: defaultDirectory });
      }}
    />
  );
}
