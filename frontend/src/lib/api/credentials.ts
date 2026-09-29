// frontend/src/lib/api/credentials.ts — the approvals half of /api/v1/credentials
// (spec credentials, secret boundary). Wire types are aliases of the
// credentials contract's generated schemas.
//
// Only the routes a page may call with its token alone live here: listing the
// pending approvals and rejecting one. Approving — like revealing a value or
// writing a key backup — needs a presence grant only the desktop shell can
// sign, so it goes through `@/lib/tauri`, never through a request from here.
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/credentials";

type Schemas = components["schemas"];

/** A change waiting for a present human in the desktop app. */
export type Approval = Schemas["ApprovalOut"];

export type ApprovalList = Schemas["ApprovalListOut"];

export const credentialsApi = {
  /** Every approval still waiting, newest first. */
  pendingApprovals: () => call<ApprovalList>("/credentials/approvals?status=pending"),
  /** Refuse one. Needs no presence: refusing only narrows what is sent. */
  rejectApproval: (id: string) =>
    call<Approval>(`/credentials/approvals/${enc(id)}/reject`, { method: "POST" }),
};
