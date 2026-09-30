// frontend/src/lib/api/credentials.ts — /api/v1/credentials: the stored secrets
// and the approvals they can wait on (spec credentials). Wire types are aliases
// of the credentials contract's generated schemas.
//
// Only the routes a page may call with its token alone live here: listing,
// storing, deleting, scanning for plaintext and importing it, listing the
// pending approvals, rejecting one, and reading whether approval is required.
// None of them returns a value. Approving — like revealing a value or writing
// a key backup — needs a presence grant only the desktop shell can sign, so it
// goes through `@/lib/tauri`, never through a request from here.
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/credentials";

type Schemas = components["schemas"];

/** A change waiting for a present human in the desktop app. */
export type Approval = Schemas["ApprovalOut"];

export type ApprovalList = Schemas["ApprovalListOut"];

export type SecretBoundarySettings = Schemas["SecretBoundarySettingsOut"];

/** One stored or cited ref: presence and what uses it, never a value. */
export type CredentialRef = Schemas["CredentialRefOut"];
export type CredentialList = Schemas["CredentialListOut"];
/** The 202 answer to a write whose new value waits for approval. */
export type CredentialWrite = Schemas["CredentialWriteOut"];
export type SecretScan = Schemas["SecretScanOut"];
export type SecretScanFinding = Schemas["SecretScanFindingOut"];
export type SecretImport = Schemas["SecretImportOut"];

/** A ref in a URL path: each segment encoded, the slashes kept (`/{ref:path}`). */
const refPath = (ref: string) => ref.split("/").map(enc).join("/");

export const credentialsApi = {
  /** Every stored ref and every ref a resource cites, with what uses it. */
  list: () => call<CredentialList>("/credentials"),
  /** Store a value: `undefined` when stored (204), the approval when it waits (202). */
  set: (ref: string, value: string) =>
    call<CredentialWrite | undefined>("/credentials", { method: "POST", body: { ref, value } }),
  /** Delete a ref; refused with `CREDENTIAL_IN_USE` while something cites it. */
  remove: (ref: string) => call<void>(`/credentials/${refPath(ref)}`, { method: "DELETE" }),
  /** Plaintext secrets found in files — where they are, never what they are. */
  scan: () => call<SecretScan>("/credentials/scan", { method: "POST" }),
  /** Move the chosen findings into the store; `dryRun` writes nothing. */
  importFindings: (ids: string[], dryRun: boolean) =>
    call<SecretImport>("/credentials/import", {
      method: "POST",
      body: { ids, dry_run: dryRun },
    }),
  /** Every approval still waiting, newest first. */
  pendingApprovals: () => call<ApprovalList>("/credentials/approvals?status=pending"),
  /** Whether the approval requirement is on, and the approval that would switch it off. */
  secretBoundary: () => call<SecretBoundarySettings>("/settings/secret-boundary"),
  /** Refuse one. Needs no presence: refusing only narrows what is sent. */
  rejectApproval: (id: string) =>
    call<Approval>(`/credentials/approvals/${enc(id)}/reject`, { method: "POST" }),
};
