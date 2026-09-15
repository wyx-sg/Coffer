// frontend/src/lib/chat/turnErrors.ts — copy for a failed chat turn.
// Most turn failures are surfaced through translateApiError (an `errors.<CODE>`
// key, else the daemon's message). A few agent-side failures arrive as free
// text with no code of their own but a clear fix the user can act on; those are
// recognised by shape here and mapped to actionable copy. Pure, so the mapping
// is unit-testable without a component.
import { translateApiError } from "@/lib/api/errors";

type Translate = (key: string) => string;

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  return error == null ? "" : String(error);
}

/** The agent CLI refused the turn because it has no login on this machine. */
export function isAgentNotLoggedIn(error: unknown): boolean {
  return /not logged in|\/login/i.test(messageOf(error));
}

/** The one-line message the turn error banner shows for `error`. */
export function describeTurnError(t: Translate, error: unknown): string {
  if (isAgentNotLoggedIn(error)) return t("chat.errors.agentNotLoggedIn");
  return translateApiError(t, error);
}
