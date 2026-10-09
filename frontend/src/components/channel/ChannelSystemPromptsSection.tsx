// frontend/src/components/channel/ChannelSystemPromptsSection.tsx
// The System prompts section of a channel's Settings: the owner's own
// instructions for direct chats and for group chats, each shown as written
// (blank when there is none), edited through the Edit button and its dialog
// rather than inline — the one part of the tab that is not saved as it changes,
// because a prompt is prose written in one go, not a value tuned field by field.
import { Pencil } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import type { ChannelSettings } from "@/lib/api/channels";
import type { ChannelEditValues } from "@/lib/channels/editChannel";
import { ChannelSystemPromptsDialog } from "./ChannelSystemPromptsDialog";

interface Props {
  settings: ChannelSettings;
  /** The tab's queued config save; resolves to whether it landed. */
  save: (values: Partial<ChannelEditValues>) => Promise<boolean>;
}

export function ChannelSystemPromptsSection({ settings, save }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const prompts = { direct: settings.direct_system_prompt, group: settings.group_system_prompt };

  return (
    <SettingsSection
      title={t("channels.settings.prompts.title")}
      description={t("channels.settings.prompts.description")}
      testId="channel-system-prompts"
      action={
        <Button
          size="sm"
          variant="outline"
          aria-label={t("channels.settings.prompts.editAria")}
          onClick={() => setOpen(true)}
        >
          <Pencil aria-hidden />
          {t("common.edit")}
        </Button>
      }
    >
      <PromptRow
        label={t("channels.settings.prompts.direct")}
        hint={t("channels.settings.prompts.directHint")}
        value={prompts.direct}
      />
      <PromptRow
        label={t("channels.settings.prompts.group")}
        hint={t("channels.settings.prompts.groupHint")}
        value={prompts.group}
      />
      <ChannelSystemPromptsDialog
        open={open}
        onOpenChange={setOpen}
        prompts={prompts}
        onSave={(next) =>
          save({ direct_system_prompt: next.direct, group_system_prompt: next.group })
        }
      />
    </SettingsSection>
  );
}

function PromptRow({ label, hint, value }: { label: string; hint: string; value: string }) {
  return (
    <SettingRow label={label} description={hint} layout="stack">
      {value ? (
        <p className="max-h-40 w-full overflow-y-auto whitespace-pre-wrap break-words text-sm text-text">
          {value}
        </p>
      ) : null}
    </SettingRow>
  );
}
