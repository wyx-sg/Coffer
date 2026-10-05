// frontend/src/components/settings/general/EditorPicker.tsx
//
// Settings › General: the editor Coffer opens managed files with.
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
import { useDetectedEditors } from "@/lib/hooks/useEditors";
import { getPreferredEditor, useSetPreferredEditor } from "@/lib/preferences";

import { CUSTOM_OPTION, DEFAULT_OPTION } from "./pickerOptions";

export function EditorPicker() {
  const { t } = useTranslation();
  const setPreferredEditor = useSetPreferredEditor();
  const { data: detected = [] } = useDetectedEditors();
  const [editor, setEditor] = useState(getPreferredEditor);
  // True once the user picks "Custom…" — keeps the text field open while it
  // is still empty. A stored value no detected editor matches is custom too.
  const [customChosen, setCustomChosen] = useState(false);

  const isDetected = detected.some((d) => d.value === editor);
  const isCustom = customChosen || (editor !== "" && !isDetected);
  const selected = isCustom ? CUSTOM_OPTION : editor === "" ? DEFAULT_OPTION : editor;

  const commitEditor = (value: string) => {
    setEditor(value);
    setPreferredEditor(value);
  };

  const pick = (value: string) => {
    if (value === CUSTOM_OPTION) {
      setCustomChosen(true);
      return;
    }
    setCustomChosen(false);
    commitEditor(value === DEFAULT_OPTION ? "" : value);
  };

  return (
    <div className="flex w-56 flex-col gap-2">
      <Select value={selected} onValueChange={pick}>
        <SelectTrigger aria-label={t("settings.general.preferredEditor")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_OPTION}>
            {t("settings.general.preferredEditorSystemDefault")}
          </SelectItem>
          {detected.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
          <SelectItem value={CUSTOM_OPTION}>
            {t("settings.general.preferredEditorCustom")}
          </SelectItem>
        </SelectContent>
      </Select>
      {isCustom ? (
        <Input
          value={editor}
          placeholder={t("settings.general.preferredEditorCustomPlaceholder")}
          onChange={(e) => setEditor(e.target.value)}
          onBlur={(e) => commitEditor(e.target.value.trim())}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
          aria-label={t("settings.general.preferredEditorCustomCommand")}
        />
      ) : null}
    </div>
  );
}
