// frontend/src/components/channel/ChannelSettingsTab.tsx
// A channel's Settings, saved as they change — there is no Save button. A
// quiet indicator at the top says Saving… / Saved / Couldn't save. The
// sections: its name, the turn settings (ChannelTurnSettingsFields), credentials
// (SeaTalk's App ID is editable; a secret is shown masked and replaced
// through a dialog), the machine that runs it, and the danger zone.
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Loader2 } from "lucide-react";

import { ResourceTitleField } from "@/components/resource/ResourceTitleField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";
import { useChannelAutoSave, CHANNEL_KIND, type AutoSaveState } from "@/lib/hooks/useChannels";
import { useSetResourceTitle } from "@/lib/hooks/useResourceMutations";
import { titlePatchValue } from "@/lib/resourceTitle";
import { ChannelMachineSelect, MachineBindingHelp } from "./ChannelMachineSelect";
import { ChannelTurnSettingsFields } from "./ChannelTurnSettingsFields";
import { FieldError } from "./FieldError";
import { useSettingDraft } from "./useSettingDraft";

function SavedIndicator({ state }: { state: AutoSaveState }) {
  const { t } = useTranslation();
  if (state === "idle") return null;
  return (
    <span
      role="status"
      data-testid="channel-save-state"
      className={state === "error" ? "text-xs text-danger" : "text-xs text-text-muted"}
    >
      {state === "saving" ? (
        <Loader2 className="mr-1 inline size-3.5 animate-spin" aria-hidden />
      ) : state === "saved" ? (
        <Check className="mr-1 inline size-3.5" aria-hidden />
      ) : null}
      {t(`channels.settings.saveState.${state}`)}
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 text-sm font-semibold">{title}</legend>
      {children}
    </fieldset>
  );
}

const nonEmpty = (text: string) => (text.trim() === "" ? null : text.trim());

interface Props {
  channel: ResourceOut;
  onReplaceSecret: () => void;
  onDelete: () => void;
}

export function ChannelSettingsTab({ channel, onReplaceSecret, onDelete }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const { save, state } = useChannelAutoSave(channel);
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
    <div className="flex max-w-2xl flex-col gap-7" data-testid="channel-settings">
      <div className="flex min-h-5 justify-end">
        <SavedIndicator state={state} />
      </div>

      <div onBlur={title.flush}>
        <ResourceTitleField
          id={`${id}-title`}
          value={title.text}
          onChange={title.change}
          name={channel.name}
        />
        <FieldError
          id={`${id}-title-error`}
          message={setTitle.error ? translateApiError(t, setTitle.error) : undefined}
        />
      </div>

      <ChannelTurnSettingsFields channel={channel} save={save} />

      <Section title={t("channels.settings.credentials.title")}>
        {seatalk ? (
          <div className="space-y-1.5">
            <Label htmlFor={`${id}-app-id`}>{t("channels.dialog.appId")}</Label>
            <Input
              id={`${id}-app-id`}
              className="w-60"
              value={appId.text}
              autoComplete="off"
              aria-invalid={nonEmpty(appId.text) === null ? true : undefined}
              onChange={(e) => appId.change(e.target.value)}
              onBlur={appId.flush}
            />
            <FieldError
              id={`${id}-app-id-error`}
              message={
                nonEmpty(appId.text) === null ? t("channels.dialog.errors.appId") : undefined
              }
            />
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <span className="text-sm font-label">
              {seatalk ? t("channels.dialog.appSecret") : t("channels.dialog.botToken")}
            </span>
            <p className="font-mono text-xs text-text-muted">••••••••••••</p>
          </div>
          <Button size="sm" variant="outline" onClick={onReplaceSecret}>
            {t("channels.settings.credentials.replace")}
          </Button>
        </div>
        <p className="text-xs text-text-muted">{t("channels.settings.credentials.hint")}</p>
      </Section>

      <Section title={t("channels.machine.title")}>
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <span className="flex items-center gap-0.5 text-sm font-label">
              {t("channels.settings.machine.runsOn")}
              <MachineBindingHelp />
            </span>
            <p className="text-xs text-text-muted">{t("channels.settings.machine.hint")}</p>
          </div>
          <ChannelMachineSelect
            uid={channel.uid}
            name={channel.name}
            config={config}
            runsOn={runsOn}
          />
        </div>
      </Section>

      <Section title={t("channels.settings.danger.title")}>
        <div className="flex items-center justify-between gap-4 rounded-xl border border-border-subtle p-3.5">
          <div className="space-y-0.5">
            <span className="text-sm font-label">{t("channels.actions.delete")}</span>
            <p className="text-xs text-text-muted">{t("channels.settings.danger.body")}</p>
          </div>
          <Button size="sm" variant="destructive" onClick={onDelete}>
            {t("channels.settings.danger.button")}
          </Button>
        </div>
      </Section>
    </div>
  );
}
