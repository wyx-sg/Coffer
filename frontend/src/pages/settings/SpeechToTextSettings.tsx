// frontend/src/pages/settings/SpeechToTextSettings.tsx
//
// The "Speech to text" picker of the Speech-to-text section: the connection
// and model Coffer transcribes voice with (spec internal-engine "Transcribe
// speech on its own connection and model", spec provider-switching
// "Keep an independent speech-to-text default").
//
// Transcription runs on its own connection flag, `transcribe_default`. A
// gateway that serves chat completions commonly serves no
// `/audio/transcriptions` at all, so the connection is chosen for this job
// alone.
//
// Not set is the safe default rather than a fault: with no connection marked
// or no model chosen, Coffer transcribes nothing and hands the agent the audio
// file untouched. The state line says so in muted words, never as an error.
//
// Edits auto-save, like every other settings surface here (no Save button).
import { useTranslation } from "react-i18next";

import { ModelPairRow } from "@/components/settings/cofferModel/ModelPairRow";
import { useConnectionModelOptions } from "@/lib/hooks/useConnectionModelOptions";
import { useInternalEngineConfig, useSetTranscribeModel } from "@/lib/hooks/useInternalEngine";
import { useProviders, useSetTranscribeDefaultProvider } from "@/lib/hooks/useProviders";

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

  return (
    <ModelPairRow
      title={t("settings.cofferModel.stt.title")}
      description={t("settings.cofferModel.stt.description")}
      providers={providers}
      selected={selected}
      onProvider={(uid) => setTranscribeDefault.mutate(uid)}
      providerBusy={setTranscribeDefault.isPending}
      providerLabel={t("settings.transcribe.connection")}
      providerPlaceholder={t("settings.transcribe.connectionPlaceholder")}
      model={currentModel}
      options={options}
      // Clearing the model is a real answer, so it is an option rather than
      // something only the CLI can express.
      onModel={(m) => setModel.mutate(m)}
      modelBusy={setModel.isPending}
      modelLabel={t("settings.transcribe.model")}
      modelPlaceholder={t("settings.transcribe.modelPlaceholder")}
      offLabel={t("settings.transcribe.modelOff")}
      notSet={t("settings.cofferModel.stt.notSet")}
      failingTail={t("settings.cofferModel.stt.failingTail")}
      // A chat probe fails on a speech model even on a healthy endpoint, so
      // Test asks the endpoint whether it lists the chosen model instead.
      testMode="list"
    />
  );
}
