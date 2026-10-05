// src/lib/api/security.ts — the machine-level security calls behind Settings › Security.
//
// The daemon's access token (spec daemon "Rotate the token over REST and on the command line") and the master key's import (through the desktop shell) and fingerprint (spec vault-sync
// "Import a master key after showing whose key it is"). Where the master key
// lives is read through `useSecretSettings`; the export goes through the
// desktop shell (`@/lib/tauri`), because no route returns the key. Wire types
// alias the generated contracts; transport is the typed client
// (.agents/frontend.md §4).
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components as sync } from "@/lib/api/generated/vault-sync";
import { importMasterKey } from "@/lib/tauri";

export type KeyPreview = sync["schemas"]["KeyPreviewOut"];
export type KeyImport = sync["schemas"]["KeyImportOut"];

export const securityApi = {
  /** Mint a new daemon token. The old one stops working the moment this
   *  answers, so the caller installs the returned token before its next call. */
  rotateToken: () => unwrap(getApiClient().POST("/daemon/rotate-token")),

  /** This machine's key fingerprint (12 hex characters), never the key. */
  keyFingerprint: () => unwrap(getApiClient().GET("/sync/key/fingerprint")),

  /** Whose key a picked file holds, beside this machine's. Changes nothing. */
  previewKeyImport: (material: string) =>
    unwrap(getApiClient().POST("/sync/key/import/preview", { body: { material } })),

  /** Install the key a file holds; a `.cfk` backup needs its passphrase. Runs
   *  in the desktop shell: the daemon refuses an import that carries no grant
   *  from a presence check, and only the shell can sign one. */
  importKey: (material: string, passphrase: string | null): Promise<KeyImport> =>
    importMasterKey(material, passphrase),
};
