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
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/secret";

type Schemas = components["schemas"];

/** A change waiting for a present human in the desktop app. */
export type Approval = Schemas["ApprovalOut"];

/** What happened to one approval in a batch: approved, rejected, or skipped with why. */
export type ApprovalBatchResult = Schemas["BatchResultOut"];

/** One stored or cited ref: presence, its label and description, and what uses it — never a value. */
export type SecretRef = Schemas["SecretRefOut"];
/** One time the value was handed out on this Mac (a `secret_resolved` audit event). */
/** What adding a standalone secret returns: its minted ref and the URI files cite. */
export type AddedSecret = Schemas["SecretMintedOut"];
export type SecretScan = Schemas["SecretScanOut"];
export type SecretScanFinding = Schemas["SecretScanFindingOut"];
export type SecretImport = Schemas["SecretImportOut"];

export const secretsApi = {
  /** Every stored ref and every ref a resource cites, with what uses it. */
  list: () => unwrap(getApiClient().GET("/secrets")),
  /** Store a value; the daemon answers 204. */
  set: (ref: string, value: string) =>
    unwrapVoid(getApiClient().POST("/secrets", { body: { ref, value } })),
  /** Delete a ref; refused with `SECRET_IN_USE` while something cites it. */
  remove: (ref: string) =>
    unwrapVoid(getApiClient().DELETE("/secrets/{ref}", { params: { path: { ref } } })),
  /** Where this Mac last handed the value out, newest first. */
  /** Add a standalone secret under a minted id, labelled `label` (and described); answers its ref and URI. */
  add: (label: string, value: string, description?: string) =>
    unwrap(
      getApiClient().POST("/secrets", {
        body: description ? { label, description, value } : { label, value },
      }),
    ) as Promise<AddedSecret>,
  /** Set a ref's label and description (an empty one removes it); the ref never changes. */
  setNotes: (ref: string, notes: { label?: string; description?: string }) =>
    unwrap(getApiClient().PUT("/secrets/notes", { body: { ref, ...notes } })),
  /** Plaintext secrets in skills and MCP servers — where they are, never what they are. */
  scan: () => unwrap(getApiClient().POST("/secrets/scan")),
  /** Remember the chosen findings' values as not secrets; answers the scan again. */
  ignoreFindings: (ids: string[]) =>
    unwrap(getApiClient().POST("/secrets/scan/ignore", { body: { ids } })),
  /** Forget them, so the scan reports them again; answers the scan again. */
  unignoreFindings: (ids: string[]) =>
    unwrap(getApiClient().POST("/secrets/scan/unignore", { body: { ids } })),
  /** Move the chosen findings into the store; `dryRun` writes nothing. */
  importFindings: (ids: string[], dryRun: boolean) =>
    unwrap(getApiClient().POST("/secrets/import", { body: { ids, dry_run: dryRun } })),
  /** Every approval still waiting, newest first. */
  pendingApprovals: () =>
    unwrap(getApiClient().GET("/secrets/approvals", { params: { query: { status: "pending" } } })),
  /** The refused approvals for one destination (a channel, a tool group): what Ask again answers. */
  rejectedApprovalsFor: (destinationUid: string) =>
    unwrap(
      getApiClient().GET("/secrets/approvals", {
        params: { query: { status: "rejected", destination_uid: destinationUid } },
      }),
    ),
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
  /** Ask to let `coffer run` hand a standalone secret to local programs; records an approval a
   *  person applies in the desktop app. */
  requestLocalAccess: (name: string) =>
    unwrap(getApiClient().POST("/secrets/local-access/request", { body: { name } })),
  /** Withdraw that grant. Needs no presence: revoking only narrows. */
  revokeLocalAccess: (name: string) =>
    unwrap(getApiClient().POST("/secrets/local-access/revoke", { body: { name } })),
  /** Ask again for a refused binding: answers the approvals now waiting. Needs no presence:
   *  asking grants nothing. */
  askAgain: (id: string) =>
    unwrap(
      getApiClient().POST("/secrets/approvals/{approval_id}/ask-again", {
        params: { path: { approval_id: id } },
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
