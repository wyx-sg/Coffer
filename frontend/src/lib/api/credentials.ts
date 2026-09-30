// frontend/src/lib/api/credentials.ts — the approvals half of /api/v1/credentials
// (spec credentials, secret boundary). Wire types are aliases of the
// credentials contract's generated schemas.
//
// Only the routes a page may call with its token alone live here: listing the
// pending approvals, rejecting one, and reading whether approval is required. Approving — like revealing a value or
// writing a key backup — needs a presence grant only the desktop shell can
// sign, so it goes through `@/lib/tauri`, never through a request from here.
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/credentials";

type Schemas = components["schemas"];

/** A change waiting for a present human in the desktop app. */
export type Approval = Schemas["ApprovalOut"];

export type ApprovalList = Schemas["ApprovalListOut"];

export type SecretBoundarySettings = Schemas["SecretBoundarySettingsOut"];

/** Every stored or cited ref — presence and references, never a value. */
export type CredentialList = Schemas["CredentialListOut"];

export const credentialsApi = {
  /** Every stored ref and every ref a resource cites (presence only). */
  listRefs: () => call<CredentialList>("/credentials"),
  /** Every approval still waiting, newest first. */
  pendingApprovals: () => call<ApprovalList>("/credentials/approvals?status=pending"),
  /** Whether the approval requirement is on, and the approval that would switch it off. */
  secretBoundary: () => call<SecretBoundarySettings>("/settings/secret-boundary"),
  /** Refuse one. Needs no presence: refusing only narrows what is sent. */
  rejectApproval: (id: string) =>
    call<Approval>(`/credentials/approvals/${enc(id)}/reject`, { method: "POST" }),
};
