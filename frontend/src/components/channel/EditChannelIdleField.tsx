// frontend/src/components/channel/EditChannelIdleField.tsx
// The Conversations section of a channel's Settings tab — spec channels "Open a
// new conversation after an idle period": how many hours a chat may sit quiet
// before its next message opens a new conversation (0 never does).
//
// The draft holds the raw text so a blank or out-of-range entry is shown as an
// error and never saved, instead of being silently coerced.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { IDLE_HOURS_MAX, IDLE_HOURS_MIN, parseIdleHours } from "./channelTurnSettings";

export function EditChannelIdleField({
  value,
  onChange,
}: {
  /** The idle period in hours, as typed. */
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const invalid = parseIdleHours(value) === null;

  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 text-sm font-semibold">{t("channels.edit.idle.title")}</legend>
      <div className="space-y-1.5">
        <Label htmlFor={id}>{t("channels.edit.idle.label")}</Label>
        <p id={helpId} className="text-xs text-text-muted">
          {t("channels.edit.idle.hint")}
        </p>
        <div className="flex items-center gap-2">
          <Input
            id={id}
            type="number"
            inputMode="decimal"
            step="any"
            min={IDLE_HOURS_MIN}
            max={IDLE_HOURS_MAX}
            className="w-28"
            value={value}
            aria-invalid={invalid ? true : undefined}
            aria-describedby={invalid ? `${helpId} ${errorId}` : helpId}
            onChange={(e) => onChange(e.target.value)}
          />
          <span className="text-sm text-text-muted">{t("channels.edit.idle.unit")}</span>
        </div>
        {invalid ? (
          <p id={errorId} className="text-xs text-danger" role="alert">
            {t("channels.edit.idle.invalid", { min: IDLE_HOURS_MIN, max: IDLE_HOURS_MAX })}
          </p>
        ) : null}
      </div>
    </fieldset>
  );
}
