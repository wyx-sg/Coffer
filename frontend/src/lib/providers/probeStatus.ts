// src/lib/providers/probeStatus.ts — what the endpoint-models probe says about a provider's health.
//
// `POST /models/list-models` never fails the request: it answers with the
// models it listed, a message, and `reachable` — false only when the listing
// call itself failed (the message then carries the reason). So health is read
// from that answer: reachable (models listed, or an honest empty catalogue);
// not reachable with a reason naming 401/403 → the key is rejected; any other
// failure, or a failed request → unreachable.

export type ProbeStatus = "checking" | "reachable" | "keyRejected" | "unreachable";

const AUTH_RE =
  /\b(401|403)\b|unauthori[sz]ed|forbidden|invalid[\s_-]*(api[\s_-]*)?key|authentication/i;

interface ProbeAnswer {
  models: readonly unknown[];
  message: string;
  reachable: boolean;
}

/** Whether a probe message names an authentication failure. */
export function isAuthFailure(message: string | null | undefined): boolean {
  return !!message && AUTH_RE.test(message);
}

/** The HTTP status a failure message carries, when it names 401 or 403. */
export function authStatusOf(message: string | null | undefined): string | null {
  return message?.match(/\b(401|403)\b/)?.[1] ?? null;
}

/** The probe failed to list: a failed request, or an answer that is not reachable. */
export function probeFailed(data: ProbeAnswer | undefined, error: unknown): boolean {
  if (error != null) return true;
  return !!data && !data.reachable;
}

export function probeStatus(opts: {
  data: ProbeAnswer | undefined;
  error: unknown;
  pending: boolean;
}): ProbeStatus {
  const { data, error, pending } = opts;
  if (error != null) return "unreachable";
  if (pending || !data) return "checking";
  if (data.reachable) return "reachable";
  return isAuthFailure(data.message) ? "keyRejected" : "unreachable";
}
