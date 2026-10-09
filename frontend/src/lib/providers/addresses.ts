// src/lib/providers/addresses.ts — a connection as its two addresses: where it serves the OpenAI wire and the Anthropic wire.
//
// The Add and Edit dialogs ask for addresses, not a protocol (ADR
// one-connection-serves-both-wires): Codex uses the OpenAI-compatible one,
// Claude Code the Anthropic-compatible one. The stored shape is still
// `protocol` + `base_url` + an optional `anthropic_base_url`, derived here: an
// OpenAI address makes the connection `openai` with the Anthropic address as
// its second; an Anthropic address alone makes it `anthropic`.
import type { Protocol, Provider } from "@/lib/api/providers";
import type { Preset } from "./presets";

export interface Addresses {
  openai: string;
  anthropic: string;
}

/** Which address fields a form shows. */
export interface AddressFields {
  openai: boolean;
  anthropic: boolean;
}

export interface Endpoint {
  protocol: Protocol;
  baseUrl: string;
  /** `null`: no second address. */
  anthropicBaseUrl: string | null;
}

/** The stored endpoint the typed addresses stand for; `null` when both are blank. */
export function endpointOf(a: Addresses): Endpoint | null {
  const openai = a.openai.trim();
  const anthropic = a.anthropic.trim();
  if (openai) return { protocol: "openai", baseUrl: openai, anthropicBaseUrl: anthropic || null };
  if (anthropic) return { protocol: "anthropic", baseUrl: anthropic, anthropicBaseUrl: null };
  return null;
}

type Stored = Pick<Provider, "protocol" | "base_url"> & { anthropic_base_url?: string | null };

/** A saved connection's addresses. An `unknown` wire was never told apart, so
 *  its one address stands in both fields. */
export function addressesOf(p: Stored): Addresses {
  switch (p.protocol) {
    case "anthropic":
      return { openai: "", anthropic: p.base_url };
    case "unknown":
      return { openai: p.base_url, anthropic: p.base_url };
    default:
      return { openai: p.base_url, anthropic: p.anthropic_base_url ?? "" };
  }
}

/** The fields a saved connection's Edit dialog shows: a local runtime keeps the
 *  one address detection found; any other connection may name both. */
export function fieldsOf(p: Stored & Pick<Provider, "local_runtime">): AddressFields {
  if (!p.local_runtime) return { openai: true, anthropic: true };
  return { openai: p.protocol !== "anthropic", anthropic: p.protocol === "anthropic" };
}

/** Which of a vendor's regions an address set is for. */
export type Region = "intl" | "cn";

/** The addresses a vendor preset fills in, for `region` when it has one. */
export function presetAddresses(preset: Preset, region: Region = "intl"): Addresses {
  if (preset.protocol === "anthropic") return { openai: "", anthropic: preset.baseUrl };
  const at = region === "cn" && preset.cn ? preset.cn : preset;
  return { openai: at.baseUrl, anthropic: at.anthropicBaseUrl ?? "" };
}

/** The fields a vendor preset shows: the addresses the vendor has, and both for Custom. */
export function presetFields(preset: Preset): AddressFields {
  if (preset.id === "custom") return { openai: true, anthropic: true };
  const a = presetAddresses(preset);
  return { openai: a.openai !== "", anthropic: a.anthropic !== "" };
}
