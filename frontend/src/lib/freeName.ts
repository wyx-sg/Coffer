// src/lib/freeName.ts
// The rule for a free-text resource name — what a person types as the name of a
// provider connection or a channel. Any display text (spaces, Chinese, emoji),
// trimmed, 1–80 characters, no line breaks or control characters, not starting
// with "-". The daemon enforces the same rule and answers 409
// RESOURCE_ALREADY_EXISTS for a name already taken (compared ignoring case); this
// is only the early, local half of it.
import { z } from "zod";

/** The longest name the daemon accepts. */
const FREE_NAME_MAX = 80;

export type FreeNameProblem = "required" | "tooLong" | "lineBreak" | "leadingDash";

/** Line breaks, other C0/C1 control characters, and the Unicode line/paragraph separators. */
function hasControlChar(text: string): boolean {
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    if (code < 0x20 || (code >= 0x7f && code <= 0x9f) || code === 0x2028 || code === 0x2029) {
      return true;
    }
  }
  return false;
}

/** What is wrong with `raw` as a name, or `null` when it is fine. */
export function freeNameProblem(raw: string): FreeNameProblem | null {
  const text = raw.trim();
  if (text === "") return "required";
  if ([...text].length > FREE_NAME_MAX) return "tooLong";
  if (hasControlChar(text)) return "lineBreak";
  if (text.startsWith("-")) return "leadingDash";
  return null;
}

/** A zod string that trims and applies the rule; `message` turns a problem into the text shown. */
export function freeNameSchema(message: (problem: FreeNameProblem) => string) {
  return z
    .string()
    .trim()
    .superRefine((value, ctx) => {
      const problem = freeNameProblem(value);
      if (problem) ctx.addIssue({ code: "custom", message: message(problem) });
    });
}

/** The i18n key of the message for a problem. */
export function freeNameErrorKey(problem: FreeNameProblem): string {
  return `resources.freeName.errors.${problem}`;
}
