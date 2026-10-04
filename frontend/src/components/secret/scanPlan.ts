// src/components/secret/scanPlan.ts — pure helpers the Find plaintext keys dialog reads the scan and its dry run through.
//
// A scan names where each plaintext value is, never the value (spec secret
// "Move plaintext secrets in managed resources into the store"). A dry run
// answers what an import would move; the review step shows it as the secrets
// that would be added and the skills' files and servers that would change.
import type { SecretImport, SecretScanFinding } from "@/lib/api/secret";

/** A skill file's path from its skill's folder (`deploy/scripts/run.sh`), else the home directory as `~`. */
function skillPath(path: string, skill: string): string {
  const marker = `/skills/${skill}/`;
  const at = path.lastIndexOf(marker);
  if (at >= 0) return `${skill}/${path.slice(at + marker.length)}`;
  return path.replace(/^\/(?:Users|home)\/[^/]+(?=\/)/, "~");
}

/** Where a finding sits, as one short line: `path:line` for a skill, `env KEY` / `header KEY` for a server. */
export function placeOf(f: SecretScanFinding): string {
  if (f.source === "mcp_server") return `${f.field ?? "env"} ${f.key}`;
  const path = f.path ? skillPath(f.path, f.resource) : f.resource;
  return f.line && f.line > 0 ? `${path}:${f.line}` : path;
}

/** How many skills and MCP servers the findings are in. */
export function resourceCount(findings: SecretScanFinding[]): number {
  return new Set(findings.map((f) => `${f.source}:${f.resource}`)).size;
}

export interface ImportPlan {
  /** Each secret the import would add, once, in the order first met. */
  secrets: string[];
  /** Each skill file or server it would change, once. */
  targets: string[];
  /** How many findings would move — the count Review promised. */
  moves: number;
}

/** What a dry run says would change: the secrets added and the files or servers rewritten. */
export function planOf(result: SecretImport, findings: SecretScanFinding[]): ImportPlan {
  const byId = new Map(findings.map((f) => [f.id, f]));
  // A server's ref is minted by the import itself, so a dry run names it by server and key.
  const secrets = [
    ...new Set(
      result.moved.map((m) => {
        const f = byId.get(m.id);
        return m.name ?? (f ? `${f.resource} · ${f.key}` : (m.ref ?? m.resource));
      }),
    ),
  ];
  const targets = [
    ...new Set(
      result.moved.map((m) => {
        const f = byId.get(m.id);
        return m.source === "skill" && f?.path ? skillPath(f.path, f.resource) : m.resource;
      }),
    ),
  ];
  return { secrets, targets, moves: result.moved.length };
}

/** The number of changes the Apply button counts. */
export function changeCount(plan: ImportPlan): number {
  return plan.moves;
}
