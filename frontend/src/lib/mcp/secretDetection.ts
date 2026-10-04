// frontend/src/lib/mcp/secretDetection.ts
//
// Which pasted env / header values Coffer offers as secrets by default. The
// user confirms or flips each one in the review step; this only picks the
// starting position of the toggle.

import type { ParsedEnvVar } from "./pasteTypes";

/** Env var / header names whose value Coffer treats as a secret by default. */
const SECRET_NAME_RE = /token|secret|pass|pwd|key|cred|auth/i;

/**
 * Values that *look* like a secret regardless of the var name. Mirrors the
 * backend's `_SECRET_PATTERNS` (server_config.py) so a secret-valued var
 * with an innocuous name (e.g. `SLACK_URL: "Bearer xoxb-…"`) is steered into
 * the encrypted secret store in the review step instead of being POSTed
 * inline and rejected with a CONFIG_INVALID the user can't easily action.
 */
const SECRET_VALUE_RE = /^(?:Bearer\s+|ghp_|gho_|github_pat_|sk-|xox[abp]-|eyJ[A-Za-z0-9_-]{20,})/;

/** Whether an env var or header named `key` holding `value` looks secret.
 *  An `Authorization` header (any value, `Bearer …` included) always does. */
function looksSecret(key: string, value: string): boolean {
  return SECRET_NAME_RE.test(key) || SECRET_VALUE_RE.test(value);
}

/** One reviewable pair, its Secret toggle defaulted by `looksSecret`. */
export function envVar(key: string, value: string): ParsedEnvVar {
  return { key, value, isSecret: looksSecret(key, value) };
}

/** `base` entries overlaid by `over` entries of the same key (`over` wins). */
export function mergeByKey(base: ParsedEnvVar[], over: ParsedEnvVar[]): ParsedEnvVar[] {
  const keys = new Set(over.map((e) => e.key));
  return [...base.filter((e) => !keys.has(e.key)), ...over];
}
