// frontend/src/components/channel/EditChannelBurstFields.tsx
// The message-batching half of the edit-channel form — spec channels "Take a
// burst of messages as one turn": how long the channel waits for the chat to go
// quiet before running the held messages as one turn. Two seconds fields, one
// after a text message and a longer one after a forwarded record or text-less
// files. They apply to every channel type, direct chats and groups alike.
//
// The draft holds the raw text so a blank or out-of-range entry can be shown
// as an error (and block Save) instead of being silently coerced.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BURST_WAIT_MAX, BURST_WAIT_MIN, parseBurstWait } from "./editChannel";

/** The two batching windows, as typed (seconds). */
export interface ChannelBurstDraft {
  waitAfterText: string;
  waitAfterForward: string;
}

function SecondsRow({
  label,
  help,
  value,
  onValueChange,
}: {
  label: string;
  help: string;
  value: string;
  onValueChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const invalid = parseBurstWait(value) === null;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          step={0.5}
          min={BURST_WAIT_MIN}
          max={BURST_WAIT_MAX}
          className="w-28"
          value={value}
          aria-invalid={invalid ? true : undefined}
          aria-describedby={invalid ? `${helpId} ${errorId}` : helpId}
          onChange={(e) => onValueChange(e.target.value)}
        />
        <span className="text-sm text-muted-foreground">{t("channels.edit.burst.unit")}</span>
      </div>
      <p id={helpId} className="text-xs text-muted-foreground">
        {help}
      </p>
      {invalid ? (
        <p id={errorId} className="text-xs text-destructive" role="alert">
          {t("channels.edit.burst.invalid", { min: BURST_WAIT_MIN, max: BURST_WAIT_MAX })}
        </p>
      ) : null}
    </div>
  );
}

export function EditChannelBurstFields({
  draft,
  onChange,
}: {
  draft: ChannelBurstDraft;
  onChange: (patch: Partial<ChannelBurstDraft>) => void;
}) {
  const { t } = useTranslation();

  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 text-sm font-medium">{t("channels.edit.burst.title")}</legend>
      <SecondsRow
        label={t("channels.edit.burst.waitAfterText")}
        help={t("channels.edit.burst.waitAfterTextHint")}
        value={draft.waitAfterText}
        onValueChange={(waitAfterText) => onChange({ waitAfterText })}
      />
      <SecondsRow
        label={t("channels.edit.burst.waitAfterForward")}
        help={t("channels.edit.burst.waitAfterForwardHint")}
        value={draft.waitAfterForward}
        onValueChange={(waitAfterForward) => onChange({ waitAfterForward })}
      />
    </fieldset>
  );
}
