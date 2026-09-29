// src/pages/ModelProvidersPage.tsx — Model providers (spec provider-switching "Offer every connection operation on REST, CLI and web").
//
// One list + detail page: a provider is an endpoint, a protocol, the models it
// offers and a key taken from a secret reference. At `/model-providers` the
// list opens on its first provider; with none yet, the page is the welcome
// panel. There are no library tabs: which agent runs on what is shown and
// switched on each agent's Model tab, and Coffer's own model is chosen in
// Settings › General. The layout is ProvidersSplit, shared with the detail
// route so the list does not re-lay out between the two.
import { ProvidersSplit } from "@/components/providers/ProvidersSplit";

export function ModelProvidersPage() {
  return <ProvidersSplit />;
}
