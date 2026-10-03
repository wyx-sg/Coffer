// src/pages/ModelProvidersPage.tsx — Model providers (spec provider-switching "Offer every connection operation on REST, CLI and web").
//
// Two tabs under one header: Providers (a list + detail page: a provider is an
// endpoint, a protocol, the models it offers and a key taken from a secret
// reference) and Usage (what the proxy metered for API-key requests). The tab
// is in the URL: `/model-providers` is Providers, `/model-providers?tab=usage`
// is Usage. At `/model-providers` the list opens on its first provider; with
// none yet, the page is the welcome panel. There are no library tabs: which
// agent runs on what is shown and switched on each agent's Model tab, and
// Coffer's own model is chosen in Settings › General. The Providers layout is
// ProvidersSplit, shared with the detail route so the list does not re-lay out
// between the two.
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AddProviderDialog } from "@/components/providers/AddProviderDialog";
import { ProvidersHeader } from "@/components/providers/ProvidersHeader";
import { ProvidersSplit } from "@/components/providers/ProvidersSplit";
import { UsageTab } from "@/components/usage/UsageTab";
import type { PresetId } from "@/lib/providers/presets";
import { providersTabPath } from "@/lib/providers/tabs";

function UsageView() {
  const navigate = useNavigate();
  const [adding, setAdding] = useState<PresetId | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <ProvidersHeader tab="usage" onAdd={() => setAdding("anthropic")} />
      <UsageTab
        onOpenProviders={() => navigate(providersTabPath("providers"), { replace: true })}
      />
      <AddProviderDialog
        preset={adding}
        onClose={() => setAdding(null)}
        onCreated={(p) => navigate(`/model-providers/${encodeURIComponent(p.uid)}`)}
      />
    </div>
  );
}

export function ModelProvidersPage() {
  const [params] = useSearchParams();
  return params.get("tab") === "usage" ? <UsageView /> : <ProvidersSplit />;
}
