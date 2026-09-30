// frontend/src/components/channel/EditChannelReplyFields.tsx
// The Replies section of a channel's Settings tab: how a running turn shows
// itself in the chat. One seconds field — a turn that runs at least this long
// ends with one short "Done" ping (0 turns it off) — and one switch: list the
// last steps under the live status line, or keep only the status line.
//
// The seconds draft holds the raw text so a blank or out-of-range entry is
// shown as an error and never saved, instead of being silently coerced.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { NOTIFY_AFTER_MAX, NOTIFY_AFTER_MIN, parseNotifyAfter } from "./channelTurnSettings";

/** The two reply settings, as the form holds them. */
export interface ChannelReplyDraft {
  showSteps: boolean;
  /** The completion-ping threshold, as typed (seconds). */
  notifyAfter: string;
}

export function EditChannelReplyFields({
  draft,
  onChange,
}: {
  draft: ChannelReplyDraft;
  onChange: (patch: Partial<ChannelReplyDraft>) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const stepsId = `${id}-steps`;
  const stepsHintId = `${stepsId}-hint`;
  const notifyId = `${id}-notify`;
  const helpId = `${notifyId}-help`;
  const errorId = `${notifyId}-error`;
  const invalid = parseNotifyAfter(draft.notifyAfter) === null;

  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 text-sm font-semibold">{t("channels.edit.replies.title")}</legend>
      <div className="space-y-1.5">
        <Label htmlFor={notifyId}>{t("channels.edit.replies.notifyAfter")}</Label>
        <p id={helpId} className="text-xs text-text-muted">
          {t("channels.edit.replies.notifyAfterHint")}
        </p>
        <div className="flex items-center gap-2">
          <Input
            id={notifyId}
            type="number"
            inputMode="numeric"
            step={1}
            min={NOTIFY_AFTER_MIN}
            max={NOTIFY_AFTER_MAX}
            className="w-28"
            value={draft.notifyAfter}
            aria-invalid={invalid ? true : undefined}
            aria-describedby={invalid ? `${helpId} ${errorId}` : helpId}
            onChange={(e) => onChange({ notifyAfter: e.target.value })}
          />
          <span className="text-sm text-text-muted">{t("channels.edit.burst.unit")}</span>
        </div>
        {invalid ? (
          <p id={errorId} className="text-xs text-danger" role="alert">
            {t("channels.edit.burst.invalid", { min: NOTIFY_AFTER_MIN, max: NOTIFY_AFTER_MAX })}
          </p>
        ) : null}
      </div>
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-0.5">
          <Label htmlFor={stepsId}>{t("channels.edit.replies.showSteps")}</Label>
          <p id={stepsHintId} className="text-xs text-text-muted">
            {t("channels.edit.replies.showStepsHint")}
          </p>
        </div>
        <Switch
          id={stepsId}
          aria-describedby={stepsHintId}
          checked={draft.showSteps}
          onCheckedChange={(showSteps) => onChange({ showSteps })}
        />
      </div>
    </fieldset>
  );
}
