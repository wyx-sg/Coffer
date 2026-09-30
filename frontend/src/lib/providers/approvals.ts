// src/lib/providers/approvals.ts — the replaced key of a provider that still waits for approval.
//
// Replacing a key that is in use does not take effect at once (spec
// secret "Hold a replaced value in use until a person approves it"): the
// PATCH seals the new value behind a pending `replace_value` approval on the
// provider's secret ref. This finds that approval, if any.
import type { Approval } from "@/lib/api/secret";

export function pendingReplaceFor(
  approvals: readonly Approval[] | undefined,
  ref: string | null,
): Approval | null {
  if (!ref) return null;
  return (
    approvals?.find((a) => a.op === "replace_value" && a.ref === ref && a.status === "pending") ??
    null
  );
}
