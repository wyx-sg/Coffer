// frontend/src/pages/settings/EngineSettings.tsx
//
// Settings → Engine: how Coffer itself thinks, and what it does when nobody
// asked. Three cards, configuring Coffer's own machinery rather than anything
// served to an agent — the LLM connection and model its own passes run on plus
// the bound on one call to it, the connection and model it transcribes speech
// with, and the switch and interval of each unattended pass, curation included.
//
// Speech-to-text is a card of its own rather than a row in the engine's,
// because it runs on a SECOND connection flag with no fallback to the engine's:
// a gateway serving chat completions commonly serves no transcription endpoint
// at all (spec internal-engine "Transcribe speech on its own connection and model").
//
// The embedding card that used to sit beside it is gone with vector retrieval:
// knowledge is a directory of files an agent reads with its own tools, so there
// is no index for an embedding model to feed (ADR knowledge-is-plain-files).
import { InternalEngineSettings } from "./InternalEngineSettings";
import { SpeechToTextSettings } from "./SpeechToTextSettings";
import { UpkeepSettings } from "./UpkeepSettings";

export function EngineSettings() {
  return (
    <div className="space-y-6">
      <InternalEngineSettings />
      <SpeechToTextSettings />
      <UpkeepSettings />
    </div>
  );
}
