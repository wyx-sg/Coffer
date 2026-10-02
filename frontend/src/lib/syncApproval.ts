// frontend/src/lib/syncApproval.ts — the sync remote's push token waiting for a person.
import { ApiError } from "@/lib/api/errors";

/** The daemon held the push token for a person's approval (`SECRET_BINDING_PENDING`). */
export function isApprovalWait(error: unknown): boolean {
  return error instanceof ApiError && error.code === "SECRET_BINDING_PENDING";
}
