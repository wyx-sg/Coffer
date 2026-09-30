// src/lib/api/security.ts — the machine-level security calls behind Settings › Security.
//
// The daemon's access token (spec daemon "Rotate the token from REST or the
// command line") and the master key's import and fingerprint (spec vault-sync
// "Import a master key after showing whose key it is"). Where the master key
// lives is read through `useCredentialSettings`; the export goes through the
// desktop shell (`@/lib/tauri`), because no route returns the key. Wire types
// alias the generated contracts; transport is the shared `call`
// (.agents/frontend.md §4).
import { call } from "@/lib/api/call";
import type { components as daemon } from "@/lib/api/generated/daemon";
import type { components as sync } from "@/lib/api/generated/vault-sync";

export type TokenRotation = daemon["schemas"]["TokenRotationOut"];
export type KeyFingerprint = sync["schemas"]["KeyFingerprintOut"];
export type KeyPreview = sync["schemas"]["KeyPreviewOut"];
export type KeyImport = sync["schemas"]["KeyImportOut"];

export const securityApi = {
  /** Mint a new daemon token. The old one stops working the moment this
   *  answers, so the caller installs the returned token before its next call. */
  rotateToken: () => call<TokenRotation>("/daemon/rotate-token", { method: "POST" }),

  /** This machine's key fingerprint (12 hex characters), never the key. */
  keyFingerprint: () => call<KeyFingerprint>("/sync/key/fingerprint"),

  /** Whose key a picked file holds, beside this machine's. Changes nothing. */
  previewKeyImport: (material: string) =>
    call<KeyPreview>("/sync/key/import/preview", { method: "POST", body: { material } }),

  /** Install the key a file holds; a `.cfk` backup needs its passphrase. */
  importKey: (material: string, passphrase: string | null) =>
    call<KeyImport>("/sync/key/import", { method: "POST", body: { material, passphrase } }),
};
