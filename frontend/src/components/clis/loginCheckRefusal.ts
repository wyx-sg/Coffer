// src/components/clis/loginCheckRefusal.ts — read a login-check refusal out of a failed CLI save.
import { ApiError } from "@/lib/api/errors";

/** The command name a refused login check must start with, when that is why the save failed. */
export function loginCheckRefusal(error: unknown): { command: string } | null {
  if (!(error instanceof ApiError) || error.code !== "CLI_TOOL_INVALID") return null;
  const d = error.details as { reason?: unknown; command?: unknown } | undefined;
  return d?.reason === "login_check_command" && typeof d.command === "string"
    ? { command: d.command }
    : null;
}
