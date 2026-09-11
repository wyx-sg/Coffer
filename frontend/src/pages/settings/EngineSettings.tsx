// frontend/src/pages/settings/EngineSettings.tsx
//
// Settings → Engine: how Coffer itself thinks. Two cards, both configuring
// Coffer's own machinery rather than anything served to an agent — the LLM
// connection + model its memory organizer runs on, and the embedding model
// behind vector retrieval. They used to sit at the bottom of the
// model-provider page; that page is the connection library agents draw from,
// and internal configuration is not a resource, so it lives here instead.
import { EmbeddingSettings } from "./EmbeddingSettings";
import { InternalEngineSettings } from "./InternalEngineSettings";

export function EngineSettings() {
  return (
    <div className="space-y-6">
      <InternalEngineSettings />
      <EmbeddingSettings />
    </div>
  );
}
