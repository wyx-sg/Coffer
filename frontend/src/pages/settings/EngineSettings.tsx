// frontend/src/pages/settings/EngineSettings.tsx
//
// Settings → Engine: how Coffer itself thinks, and what it does when nobody
// asked. Two cards, configuring Coffer's own machinery rather than anything
// served to an agent — the LLM connection and model its own passes run on, and
// the switch and interval of each of those passes, curation included.
//
// The embedding card that used to sit beside it is gone with vector retrieval:
// knowledge is a directory of files an agent reads with its own tools, so there
// is no index for an embedding model to feed (ADR knowledge-is-plain-files).
import { InternalEngineSettings } from "./InternalEngineSettings";
import { UpkeepSettings } from "./UpkeepSettings";

export function EngineSettings() {
  return (
    <div className="space-y-6">
      <InternalEngineSettings />
      <UpkeepSettings />
    </div>
  );
}
