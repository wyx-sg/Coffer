// frontend/src/pages/settings/SpeechToTextSettings.tsx
//
// Settings → Engine: the connection and model Coffer transcribes voice with
// (spec internal-engine "Transcribe speech on its own connection and model",
// spec provider-switching `transcribe_default`).
//
// It is its own card, beside Coffer's model rather than inside it, because the
// two halves are deliberately independent: transcription runs on a SECOND
// connection flag, and nothing falls back between them. A gateway that serves
// chat completions commonly serves no `/audio/transcriptions` at all, so
// borrowing the engine's connection would aim every voice message at a 404 —
// which is exactly why the flag is separate and why this card asks for a
// connection of its own rather than inheriting one.
//
// The OFF state is the point of the note at the bottom. With no connection
// marked or no model chosen, Coffer transcribes nothing and hands the agent the
// audio file untouched — the recording never leaves the machine. That is the
// safe default rather than a fault, so it is stated in plain muted text, not as
// a warning Alert and not as an error: a reader landing on an unconfigured card
// should read "off, and here is what off means", never "broken".
//
// Edits auto-save, like every other settings surface here (no Save button).
import { useTranslation } from "react-i18next";
import { Mic, MicOff } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useConnectionModelOptions } from "@/lib/hooks/useConnectionModelOptions";
import { useInternalEngineConfig, useSetTranscribeModel } from "@/lib/hooks/useInternalEngine";
import { useProviders, useSetTranscribeDefaultProvider } from "@/lib/hooks/useProviders";

/** The option that stops transcription. Underscored so it cannot collide with a
 *  real model id, which is any opaque string the vendor chose. */
const OFF_VALUE = "__off__";

export function SpeechToTextSettings() {
  const { t } = useTranslation();
  const { data: providers = [] } = useProviders();
  const { data: config } = useInternalEngineConfig();
  const selected = providers.find((p) => p.transcribe_default) ?? null;
  const setTranscribeDefault = useSetTranscribeDefaultProvider();
  const setModel = useSetTranscribeModel();

  // Transcription runs a SPEECH model, so the connection's catalogue is narrowed
  // to modality `audio` — the same rule the chat picker applies with `text`.
  const currentModel = config?.transcribe_model ?? "";
  const options = useConnectionModelOptions(selected, "audio", currentModel);

  // Both halves are needed, and neither substitutes for the other.
  const on = selected !== null && currentModel !== "";
  const StateIcon = on ? Mic : MicOff;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-5 text-primary" strokeWidth={1.5} />
          {t("settings.transcribe.title")}
        </CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">{t("settings.transcribe.subtitle")}</p>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>{t("settings.transcribe.connection")}</Label>
          <Select
            // The VALUE is the connection's uid — what the route takes — and the
            // LABEL is its name.
            value={selected?.uid ?? ""}
            onValueChange={(uid) => setTranscribeDefault.mutate(uid)}
            disabled={providers.length === 0 || setTranscribeDefault.isPending}
          >
            <SelectTrigger aria-label={t("settings.transcribe.connection")}>
              <SelectValue placeholder={t("settings.transcribe.connectionPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.uid} value={p.uid}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label>{t("settings.transcribe.model")}</Label>
          <Select
            value={currentModel === "" ? OFF_VALUE : currentModel}
            onValueChange={(m) => setModel.mutate(m === OFF_VALUE ? null : m)}
            disabled={!selected || setModel.isPending}
          >
            <SelectTrigger aria-label={t("settings.transcribe.model")}>
              <SelectValue placeholder={t("settings.transcribe.modelPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {/* Clearing the model is a real answer, so it is an option rather
                  than something only the CLI can express. */}
              <SelectItem value={OFF_VALUE}>{t("settings.transcribe.modelOff")}</SelectItem>
              {options.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-start gap-2 sm:col-span-2">
          <StateIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">
              {on ? t("settings.transcribe.onTitle") : t("settings.transcribe.offTitle")}
            </span>{" "}
            {on ? t("settings.transcribe.onBody") : t("settings.transcribe.offBody")}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
