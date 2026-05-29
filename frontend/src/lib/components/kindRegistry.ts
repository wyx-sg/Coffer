// frontend/src/lib/components/kindRegistry.ts
import type { ComponentType } from "react";
import type { components } from "@/lib/api/types";

export type ResourceOut = components["schemas"]["ResourceOut"];

export interface KindUIModule {
  /** Stable kind name matching the backend's Kind.name (e.g. "mcp_server"). */
  name: string;
  /** Human display name in nav + headers. */
  displayName: string;
  /** Lucide icon name reference for sidebar nav (string so we can map at render). */
  icon?: ComponentType<{ className?: string }>;
  /** Per-kind row renderer in the resources list. */
  Card: ComponentType<{ resource: ResourceOut }>;
  /** Optional kind-specific detail page (receives the name from route params). */
  DetailPage?: ComponentType<{ name: string }>;
}

const _registry: Map<string, KindUIModule> = new Map();

export function registerKindUI(module: KindUIModule): void {
  if (_registry.has(module.name)) {
    // Re-registration is a no-op (HMR friendliness).
    return;
  }
  _registry.set(module.name, module);
}

export function getKindUI(name: string): KindUIModule | undefined {
  return _registry.get(name);
}

export function listKindUIs(): KindUIModule[] {
  return Array.from(_registry.values());
}

/** Internal test helper — DO NOT use in production code. */
export function _resetKindRegistry(): void {
  _registry.clear();
}
