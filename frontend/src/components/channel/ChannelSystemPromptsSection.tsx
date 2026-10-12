// frontend/src/components/channel/ChannelSystemPromptsSection.tsx
// The System prompt section of a channel's Settings: per chat kind, what every
// turn tells the agent, in its two parts — Coffer's channel note (how this
// channel works: files, buttons, what renders), shown read-only, and the reply
// style, Coffer's default until the owner rewrites it through the Edit button
// and its dialog (spec channels "Let the owner rewrite a channel's reply style").
import { Pencil } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow, SettingsSection } from "@/components/settings/SettingsLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ChannelPrompts, ChannelSettings } from "@/lib/api/channels";
import type { ChannelEditValues } from "@/lib/channels/editChannel";
import { ChannelSystemPromptsDialog, type ReplyStyles } from "./ChannelSystemPromptsDialog";

interface Props {
  settings: ChannelSettings;
  /** Coffer's note and default style per chat kind; null when the daemon could
   *  not compose them, and the rows then show the owner's styles only. */
  prompts: ChannelPrompts | null;
  /** The tab's queued config save; resolves to whether it landed. */
  save: (values: Partial<ChannelEditValues>) => Promise<boolean>;
}

const KINDS = ["direct", "group"] as const;

export function ChannelSystemPromptsSection({ settings, prompts, save }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // What applies now: the owner's rewrite, or Coffer's default.
  const styles: ReplyStyles = {
    direct: settings.direct_reply_style || (prompts?.direct.default_style ?? ""),
    group: settings.group_reply_style || (prompts?.group.default_style ?? ""),
  };
  const defaults: ReplyStyles | null = prompts
    ? { direct: prompts.direct.default_style, group: prompts.group.default_style }
    : null;

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
      {KINDS.map((kind) => (
        <SettingRow
          key={kind}
          label={t(`channels.settings.prompts.${kind}`)}
          description={t(`channels.settings.prompts.${kind}Hint`)}
          layout="stack"
        >
          <div className="flex w-full flex-col gap-3" data-testid={`channel-prompt-${kind}`}>
            {prompts ? (
              <PromptPart
                label={t("channels.settings.prompts.note")}
                badge={<Badge variant="secondary">{t("channels.settings.prompts.readOnly")}</Badge>}
              >
                <PromptText text={prompts[kind].channel_note} />
              </PromptPart>
            ) : null}
            <PromptPart
              label={t("channels.settings.prompts.style")}
              badge={
                <Badge variant={settings[`${kind}_reply_style`] ? "default" : "secondary"}>
                  {settings[`${kind}_reply_style`]
                    ? t("channels.settings.prompts.rewritten")
                    : t("channels.settings.prompts.default")}
                </Badge>
              }
            >
              <PromptText text={styles[kind]} />
              {prompts?.[kind].default_changed ? (
                <p className="text-xs text-warning">
                  {t("channels.settings.prompts.defaultChanged")}
                </p>
              ) : null}
            </PromptPart>
          </div>
        </SettingRow>
      ))}
      <ChannelSystemPromptsDialog
        open={open}
        onOpenChange={setOpen}
        styles={styles}
        defaults={defaults}
        onSave={(next) => save({ direct_reply_style: next.direct, group_reply_style: next.group })}
      />
    </SettingsSection>
  );
}

function PromptPart({
  label,
  badge,
  children,
}: {
  label: string;
  badge: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 text-xs font-label text-text-muted">
        {label}
        {badge}
      </div>
      {children}
    </div>
  );
}

function PromptText({ text }: { text: string }) {
  return (
    <p className="max-h-40 w-full overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border bg-surface-sunken px-3 py-2 text-sm text-text">
      {text}
    </p>
  );
}
