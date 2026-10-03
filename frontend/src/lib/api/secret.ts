// frontend/src/lib/api/secret.ts — /api/v1/secrets: the stored secrets
// and the approvals they can wait on (spec secret). Wire types are aliases
// of the secrets contract's generated schemas.
//
// Only the routes a page may call with its token alone live here: listing,
// storing, deleting, scanning for plaintext and importing it, listing the
// pending approvals, rejecting one, and reading whether approval is required.
// None of them returns a value. Approving — like revealing a value or writing
// a key backup — needs a presence grant only the desktop shell can sign, so it
// goes through `@/lib/tauri`, never through a request from here.
import { getApiClient, unwrap, unwrapOptional, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/secret";

type Schemas = components["schemas"];

/** A change waiting for a present human in the desktop app. */
export type Approval = Schemas["ApprovalOut"];

/** What happened to one approval in a batch: approved, rejected, or skipped with why. */
export type ApprovalBatchResult = Schemas["BatchResultOut"];

/** One stored or cited ref: presence and what uses it, never a value. */
export type SecretRef = Schemas["SecretRefOut"];
/** The 202 answer to a write whose new value waits for approval. */
export type SecretWrite = Schemas["SecretWriteOut"];
export type SecretScan = Schemas["SecretScanOut"];
export type SecretScanFinding = Schemas["SecretScanFindingOut"];
export type SecretImport = Schemas["SecretImportOut"];

export const secretsApi = {
  /** Every stored ref and every ref a resource cites, with what uses it. */
  list: () => unwrap(getApiClient().GET("/secrets")),
  /** Store a value: `undefined` when stored (204), the approval when it waits (202). */
  set: (ref: string, value: string): Promise<SecretWrite | undefined> =>
    unwrapOptional(getApiClient().POST("/secrets", { body: { ref, value } })),
  /** Delete a ref; refused with `SECRET_IN_USE` while something cites it. */
  remove: (ref: string) =>
    unwrapVoid(getApiClient().DELETE("/secrets/{ref}", { params: { path: { ref } } })),
  /** Plaintext secrets found in files — where they are, never what they are. */
  scan: () => unwrap(getApiClient().POST("/secrets/scan")),
  /** Move the chosen findings into the store; `dryRun` writes nothing. */
  importFindings: (ids: string[], dryRun: boolean) =>
    unwrap(getApiClient().POST("/secrets/import", { body: { ids, dry_run: dryRun } })),
  /** Every approval still waiting, newest first. */
  pendingApprovals: () =>
    unwrap(getApiClient().GET("/secrets/approvals", { params: { query: { status: "pending" } } })),
  /** Refuse several at once. Needs no presence: refusing only narrows what is sent. */
  rejectApprovals: (ids: string[]) =>
    unwrap(getApiClient().POST("/secrets/approvals/reject", { body: { ids } })),
  /** Whether the approval requirement is on, and the approval that would switch it off. */
  secretBoundary: () => unwrap(getApiClient().GET("/settings/secret-boundary")),
  /** Turn the approval requirement on (answers at once) or ask to turn it off (the answer
   *  names the approval a present human must apply in the desktop app). */
  setSecretBoundary: (requireApproval: boolean) =>
    unwrap(
      getApiClient().PUT("/settings/secret-boundary", {
        body: { require_approval: requireApproval },
      }),
    ),
  /** Refuse one. Needs no presence: refusing only narrows what is sent. */
  rejectApproval: (id: string) =>
    unwrap(
      getApiClient().POST("/secrets/approvals/{approval_id}/reject", {
        params: { path: { approval_id: id } },
      }),
    ),
};
