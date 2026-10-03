// frontend/src/lib/mcp/testFailure.ts — what a failed config test says about
// the fix. A server that exits because an environment variable is missing prints
// it on stderr ("GITLAB_PERSONAL_ACCESS_TOKEN is required"); the form then offers
// to add that variable. Reads only what the test returned.
import type { McpTestResult } from "@/lib/api/mcpTestConfig";

/** `NAME_LIKE_THIS` followed, on the same line, by a word that says it is absent. */
const NEEDS = /\b([A-Z][A-Z0-9]*_[A-Z0-9_]+)\b[^\n]*?\b(?:is |are )?(?:required|not set|missing|must be set|undefined)/;
/** "Missing environment variable: NAME" / "missing NAME". */
const MISSING_FIRST = /\bmissing\b[^\n]*?\b([A-Z][A-Z0-9]*_[A-Z0-9_]+)\b/i;

/** The variable a failed test says it needs, or null. */
export function missingVariableOf(result: McpTestResult): string | null {
  if (result.ok || result.error_code === "stored_secret_not_released") return null;
  const text = [...(result.stderr_tail ?? []), result.error_message ?? ""];
  for (const line of text) {
    const m = NEEDS.exec(line) ?? MISSING_FIRST.exec(line);
    if (m && m[1] === m[1].toUpperCase()) return m[1];
  }
  return null;
}
