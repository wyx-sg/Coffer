// frontend/src/lib/skills/notOurs.ts — the refusal of a skill delete (409 SKILL_COPY_NOT_OURS).
//
// An agent's copy of the skill is a regular folder now, not Coffer's link, and
// Coffer only removes what it made. The refusal's details name the folder and
// the agent; the delete dialogs show them and offer "Delete, keep <Agent>'s
// folder".
import { ApiError } from "@/lib/api/errors";

/** The folder a refused delete names and whose it is, or null for any other error. */
export function notOursOf(error: unknown): { path: string; agentName: string } | null {
  if (!(error instanceof ApiError) || error.code !== "SKILL_COPY_NOT_OURS") return null;
  return notOursDetails(error.details as Record<string, unknown> | undefined);
}

/** The same two facts from a bulk result's `error_details`. */
export function notOursDetails(details: Record<string, unknown> | null | undefined): {
  path: string;
  agentName: string;
} {
  const path = details?.path;
  const agent = details?.agent_name;
  return {
    path: typeof path === "string" ? path : "",
    agentName: typeof agent === "string" ? agent : "",
  };
}
