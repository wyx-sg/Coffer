// src/lib/api/security.ts — the machine-level security calls behind Settings › Security.
//
// Only the daemon's access token lives here: rotating it is a daemon route
// (spec daemon "Rotate the token from REST or the command line"), and where the
// master key lives is read through `useCredentialSettings`. Wire types alias
// the daemon contract; transport is the shared `call` (.agents/frontend.md §4).
import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/daemon";

export type TokenRotation = components["schemas"]["TokenRotationOut"];

export const securityApi = {
  /** Mint a new daemon token. The old one stops working the moment this
   *  answers, so the caller installs the returned token before its next call. */
  rotateToken: () => call<TokenRotation>("/daemon/rotate-token", { method: "POST" }),
};
