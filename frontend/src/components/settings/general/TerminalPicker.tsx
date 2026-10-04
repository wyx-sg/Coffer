// frontend/src/components/settings/general/TerminalPicker.tsx
//
// Settings › General: the preferred terminal (system, detected, or a custom template).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDetectedTerminals } from "@/lib/hooks/useTerminals";
import { getPreferredTerminal, useSetPreferredTerminal } from "@/lib/preferences";

import { CUSTOM_OPTION, DEFAULT_OPTION } from "./pickerOptions";

/** A terminal command template must hold the command it runs. */
const COMMAND_PLACEHOLDER = "{command}";

export function TerminalPicker() {
  const { t } = useTranslation();
  const setPreferredTerminal = useSetPreferredTerminal();
  const { data: detected = [] } = useDetectedTerminals();
  const [terminal, setTerminal] = useState(getPreferredTerminal);
  const [customChosen, setCustomChosen] = useState(false);
  // A template typed without {command} is refused here and never stored.
  const [missingCommand, setMissingCommand] = useState(false);

  const isDetected = detected.some((d) => d.value === terminal);
  const isCustom = customChosen || (terminal !== "" && !isDetected);
  const selected = isCustom ? CUSTOM_OPTION : terminal === "" ? DEFAULT_OPTION : terminal;

  const pick = (value: string) => {
    setMissingCommand(false);
    if (value === CUSTOM_OPTION) {
      setCustomChosen(true);
      return;
    }
    setCustomChosen(false);
    const next = value === DEFAULT_OPTION ? "" : value;
    setTerminal(next);
    setPreferredTerminal(next);
  };

  const commitTemplate = (raw: string) => {
    const template = raw.trim();
    if (template !== "" && !template.includes(COMMAND_PLACEHOLDER)) {
      setMissingCommand(true);
      return;
    }
    setMissingCommand(false);
    setTerminal(template);
    setPreferredTerminal(template);
  };

  return (
    <div className="flex w-56 flex-col gap-2">
      <Select value={selected} onValueChange={pick}>
        <SelectTrigger aria-label={t("settings.general.preferredTerminal")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_OPTION}>
            {t("settings.general.preferredTerminalSystem")}
          </SelectItem>
          {detected.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
          <SelectItem value={CUSTOM_OPTION}>
            {t("settings.general.preferredTerminalCustom")}
          </SelectItem>
        </SelectContent>
      </Select>
      {isCustom ? (
        <>
          <Input
            value={terminal}
            placeholder={t("settings.general.preferredTerminalCustomPlaceholder")}
            onChange={(e) => {
              setTerminal(e.target.value);
              setMissingCommand(false);
            }}
            onBlur={(e) => commitTemplate(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
            aria-label={t("settings.general.preferredTerminalCustomTemplate")}
            aria-invalid={missingCommand || undefined}
          />
          {missingCommand ? (
            <p role="alert" className="text-xs text-danger">
              {t("settings.general.preferredTerminalNeedsCommand")}
            </p>
          ) : (
            <p className="text-xs text-text-muted">
              {t("settings.general.preferredTerminalCustomHint")}
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
