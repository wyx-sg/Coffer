// src/lib/providers/tabs.ts — the two tabs of the Model providers page and their addresses.
export type ProvidersTab = "providers" | "usage";

/** The address of a tab: the usage tab is a query on the list route. */
export function providersTabPath(tab: ProvidersTab): string {
  return tab === "usage" ? "/model-providers?tab=usage" : "/model-providers";
}
