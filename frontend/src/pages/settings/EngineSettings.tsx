// frontend/src/pages/settings/EngineSettings.tsx
//
// Settings → Engine: how Coffer itself thinks. One card, configuring Coffer's
// own machinery rather than anything served to an agent — the LLM connection
// and model its tidy pass runs on, and whether that pass may run unattended.
//
// The embedding card that used to sit beside it is gone with vector retrieval:
// knowledge is a directory of files an agent greps, so there is no index for an
// embedding model to feed (ADR knowledge-is-plain-files).
import { InternalEngineSettings } from "./InternalEngineSettings";

export function EngineSettings() {
  return (
    <div className="space-y-6">
      <InternalEngineSettings />
    </div>
  );
}
