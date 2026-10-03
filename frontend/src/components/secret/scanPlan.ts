// src/components/secret/scanPlan.ts — pure helpers the Find plaintext keys dialog reads the scan and its dry run through.
//
// A scan names where each plaintext value is, never the value (spec
// secret "Move plaintext secret files into the store"). A dry run answers
// what an import would move; the review step shows it as the secrets that
// would be added and the files whose value would become a reference.
import type { SecretImport, SecretScanFinding } from "@/lib/api/secret";

/** A path as the user reads it: the home directory as `~`. */
export function shortPath(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+(?=\/)/, "~");
}

/** How many distinct files the findings are in. */
export function fileCount(findings: SecretScanFinding[]): number {
  return new Set(findings.map((f) => f.path)).size;
}

export interface ImportPlan {
  /** Each secret the import would add, once, in the order first met. */
  secrets: string[];
  /** Each file whose value would become a reference, once. */
  files: string[];
}

/** What a dry run says would change: the secrets added and the files rewritten. */
export function planOf(result: SecretImport): ImportPlan {
  const secrets = [...new Set(result.moved.map((m) => m.name))];
  const files = [...new Set(result.moved.map((m) => m.path))];
  return { secrets, files };
}

/** The number of changes the Apply button counts. */
export function changeCount(plan: ImportPlan): number {
  return plan.secrets.length + plan.files.length;
}

/** The hand-off prompt for a key that is saved but whose file Coffer could not rewrite: where each
 *  file is and why, never a value. */
export function permissionPrompt(unwritten: SecretImport["skipped"]): string {
  const lines = unwritten.map(
    (s) => `- ${shortPath(s.path)} (saved as the secret ${s.name ?? "?"}): ${s.reason}`,
  );
  return [
    "Coffer saved these plaintext keys as secrets but could not rewrite the files that hold them.",
    "Check each file's permissions and owner, make it writable by me, and tell me when I can retry in Coffer. Do not print, copy or move any key.",
    "",
    ...lines,
  ].join("\n");
}
