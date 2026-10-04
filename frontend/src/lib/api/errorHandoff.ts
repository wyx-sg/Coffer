// src/lib/api/errorHandoff.ts — the hand-off prompt a refusal carries, if any.
//
// Some refusals end in a chore for the person's agent rather than a retry:
// git missing (`reason: "git_missing"`) among them. The
// daemon then puts the prompt in the error envelope's details as
// `handoff: { prompt }` — the same shape as a response's `handoff` field — and
// the page that shows the error offers it through `AgentHandoff`. The text is
// the backend's; this only reads it off.
import { ApiError } from "./errors";

/** The prompt in `error.details.handoff`, or `null` when there is none. */
export function errorHandoff(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const details = error.details as { handoff?: { prompt?: unknown } | null } | undefined;
  const prompt = details?.handoff?.prompt;
  return typeof prompt === "string" && prompt ? prompt : null;
}
