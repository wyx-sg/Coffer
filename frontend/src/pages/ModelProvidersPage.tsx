// src/pages/ModelProvidersPage.tsx — Model providers: one header over two tabs, Providers | Usage.
//
// Three addresses render this one page, so moving between them keeps the
// header and the open dialog: `/model-providers` (the list opens on its first
// provider), `/model-providers/<uid>` (a provider open) and
// `/model-providers?tab=usage` (the Usage tab). Providers is a split — the list is
// the fallback order, the detail stacks Used by → Endpoint → Models; with no
// provider yet it is the first-run state. Which agent runs on what is changed
// on each agent's Change model; Coffer's own model in Settings › General.
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { AddProviderDialog } from "@/components/providers/AddProviderDialog";
import { ModelProvidersHeader } from "@/components/providers/ModelProvidersHeader";
import { ProvidersSplit } from "@/components/providers/ProvidersSplit";
import { UsageTab } from "@/components/usage/UsageTab";
import type { PresetId } from "@/lib/providers/presets";
import { providersTabPath } from "@/lib/providers/tabs";

export function ModelProvidersPage() {
  const { uid } = useParams<{ uid: string }>();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [adding, setAdding] = useState<PresetId | null>(null);
  const usage = !uid && params.get("tab") === "usage";

  return (
    // Full-bleed like Skills and Knowledge: Layout pads every page, and this
    // one is a workspace whose panes scroll on their own.
    <div className="-mx-8 -mb-10 -mt-4 flex h-screen flex-col overflow-hidden">
      <ModelProvidersHeader
        tab={usage ? "usage" : "providers"}
        onAdd={() => setAdding("anthropic")}
      />
      {usage ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-8 pb-10 pt-5">
          <UsageTab
            onOpenProviders={() => navigate(providersTabPath("providers"), { replace: true })}
          />
        </div>
      ) : (
        <ProvidersSplit uid={uid} onAdd={setAdding} />
      )}
      <AddProviderDialog
        preset={adding}
        onClose={() => setAdding(null)}
        onCreated={(p) => navigate(`/model-providers/${encodeURIComponent(p.uid)}`)}
      />
    </div>
  );
}
