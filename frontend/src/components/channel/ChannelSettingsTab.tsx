// frontend/src/components/channel/ChannelSettingsTab.tsx
// A channel's Settings, saved as they change — there is no Save button and no
// Saved line; a failed save is a toast. The sections: Connection (its name —
// any display name, kept as the resource's title — SeaTalk's App ID, the
// secret shown masked and replaced through a dialog, and the machine that runs
// it), Receiving messages (group rules and batching), Replies and
// conversations, and Working directories; the one destructive action, Delete,
// is a row at the bottom, not a section.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { SETTINGS_STACK, SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import type { ChannelSettings } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { useChannelAutoSave, CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { useSetResourceTitle } from "@/lib/hooks/useResourceMutations";
import { TITLE_MAX_LENGTH, titlePatchValue } from "@/lib/resourceTitle";
import { ChannelMachineSelect, MachineBindingHelp } from "./ChannelMachineSelect";
import {
  ChannelDirectoryFields,
  ChannelReceivingFields,
  ChannelReplyFields,
} from "./ChannelTurnSettingsFields";
import { FieldError } from "./FieldError";
import { useSettingDraft } from "./useSettingDraft";

const nonEmpty = (text: string) => (text.trim() === "" ? null : text.trim());

interface Props {
  channel: ResourceOut;
  /** The channel's typed settings, defaults filled in — what its fields start from. */
  settings: ChannelSettings;
  onReplaceSecret: () => void;
  onDelete: () => void;
}

export function ChannelSettingsTab({ channel, settings, onReplaceSecret, onDelete }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const { save } = useChannelAutoSave(channel);
  const setTitle = useSetResourceTitle();
  const config = channel.config;
  const seatalk = config.channel_type === "seatalk";

  const title = useSettingDraft(
    channel.title ?? "",
    (text) => ({ title: titlePatchValue(text) }),
    ({ title: next }) => {
      if (next !== (channel.title ?? null)) {
        setTitle.mutate({ kind: CHANNEL_KIND, uid: channel.uid, title: next });
      }
    },
  );
  const appId = useSettingDraft(
    typeof config.app_id === "string" ? config.app_id : "",
    nonEmpty,
    (v) => save({ app_id: v }),
  );
  const runsOn = typeof config.runs_on === "string" && config.runs_on ? config.runs_on : null;

  return (
    <div className={SETTINGS_STACK} data-testid="channel-settings">
      <SettingsSection
        title={t("channels.settings.connection.title")}
        description={t("channels.settings.secrets.hint")}
      >
        <div onBlur={title.flush}>
          <SettingRow
            label={t("channels.dialog.name")}
            labelFor={`${id}-title`}
            description={t("resources.titleField.hint")}
            descriptionId={`${id}-title-hint`}
            status={
              <FieldError
                id={`${id}-title-error`}
                message={setTitle.error ? translateApiError(t, setTitle.error) : undefined}
              />
            }
          >
            <Input
              id={`${id}-title`}
              className="w-64"
              value={title.text}
              maxLength={TITLE_MAX_LENGTH}
              placeholder={channel.name}
              aria-describedby={`${id}-title-hint`}
              onChange={(e) => title.change(e.target.value)}
            />
          </SettingRow>
        </div>
        {seatalk ? (
          <SettingRow
            label={t("channels.dialog.appId")}
            labelFor={`${id}-app-id`}
            status={
              <FieldError
                id={`${id}-app-id-error`}
                message={
                  nonEmpty(appId.text) === null ? t("channels.dialog.errors.appId") : undefined
                }
              />
            }
          >
            <Input
              id={`${id}-app-id`}
              className="w-60"
              value={appId.text}
              autoComplete="off"
              aria-invalid={nonEmpty(appId.text) === null ? true : undefined}
              onChange={(e) => appId.change(e.target.value)}
              onBlur={appId.flush}
            />
          </SettingRow>
        ) : null}
        <SettingRow
          label={seatalk ? t("channels.dialog.appSecret") : t("channels.dialog.botToken")}
          description={<span className="font-mono">••••••••••••</span>}
        >
          <Button size="sm" variant="outline" onClick={onReplaceSecret}>
            {t("channels.settings.secrets.replace")}
          </Button>
        </SettingRow>
        <SettingRow
          label={
            <span className="flex items-center gap-0.5">
              {t("channels.settings.machine.runsOn")}
              <MachineBindingHelp />
            </span>
          }
          description={t("channels.settings.machine.hint")}
        >
          <ChannelMachineSelect
            uid={channel.uid}
            name={channel.name}
            config={config}
            runsOn={runsOn}
          />
        </SettingRow>
      </SettingsSection>

      <SettingsSection
        title={t("channels.settings.receiving.title")}
        description={t("channels.settings.receiving.description")}
      >
        <ChannelReceivingFields settings={settings} save={save} />
      </SettingsSection>

      <SettingsSection title={t("channels.settings.replying.title")}>
        <ChannelReplyFields settings={settings} save={save} />
      </SettingsSection>

      <SettingsSection
        title={t("channels.edit.directories.title")}
        description={t("channels.settings.directories.description")}
        testId="channel-directories"
      >
        <ChannelDirectoryFields settings={settings} save={save} />
      </SettingsSection>

      {/* The one destructive action is a row, not a section of its own. */}
      <div className="flex min-h-setting-row items-center justify-between gap-4 border-t border-border-subtle py-2.5">
        <div className="min-w-0">
          <p className="text-sm font-medium text-text">{t("channels.actions.delete")}</p>
          <p className="text-xs text-text-muted">{t("channels.settings.danger.body")}</p>
        </div>
        <Button size="sm" variant="danger" onClick={onDelete}>
          {t("channels.settings.danger.button")}
        </Button>
      </div>
    </div>
  );
}
