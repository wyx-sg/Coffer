// frontend/scripts/codegen.mjs — `npm run codegen`.
//
// Generates one TypeScript module per OpenAPI contract under
// `specs/<spec-id>/contracts/api.openapi.yaml` into
// `src/lib/api/generated/<spec-id>.ts`, through the openapi-typescript CLI so
// the output (and its "auto-generated" header the file-size gate keys on) is
// byte-identical to what the CLI would write by hand. A spec id may be a
// nested path (`channels/telegram`), in which case the generated module nests
// to match.
//
// `codegen-check.mjs` imports `CONTRACTS` and `generate()` from here and
// regenerates into a temp dir to detect drift, so the list below is the single
// place a contract is added.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const FRONTEND_ROOT = path.resolve(here, "..");
export const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");
export const GENERATED_DIR = path.join(FRONTEND_ROOT, "src", "lib", "api", "generated");

/**
 * Every contract the frontend consumes, by spec id. A spec id is the spec
 * directory's path under `specs/`, so it is a bare folder name for a top-level
 * spec and a slash-joined path for a nested child (`channels/telegram`). The
 * generated module mirrors it: `generated/<id>.ts`, i.e.
 * `generated/channels/telegram.ts`. Always spell an id with forward slashes —
 * `specPath()` splits on them so the same list works on Windows.
 */
export const CONTRACTS = [
  "mcp-gateway",
  "agent-registry",
  "channels",
  "knowledge",
  "provider-switching",
  "skill-manager",
  "vault-sync",
];

/** Native-separator path segments for a spec id. */
function specSegments(id) {
  return id.split("/");
}

export function contractPath(id) {
  return path.join(REPO_ROOT, "specs", ...specSegments(id), "contracts", "api.openapi.yaml");
}

/** Where a spec id's generated module lands under `dir`. */
export function generatedPath(dir, id) {
  const segments = specSegments(id);
  segments[segments.length - 1] += ".ts";
  return path.join(dir, ...segments);
}

/** Generate every contract into `outDir`, returning the written file paths. */
export function generate(outDir, { quiet = false } = {}) {
  mkdirSync(outDir, { recursive: true });
  const cli = path.join(FRONTEND_ROOT, "node_modules", "openapi-typescript", "bin", "cli.js");
  const written = [];
  for (const id of CONTRACTS) {
    const out = generatedPath(outDir, id);
    // A child spec's module sits one level deeper than `outDir`, and the CLI
    // will not create that directory for us.
    mkdirSync(path.dirname(out), { recursive: true });
    execFileSync(process.execPath, [cli, contractPath(id), "-o", out], {
      cwd: FRONTEND_ROOT,
      stdio: quiet ? ["ignore", "ignore", "inherit"] : "inherit",
    });
    written.push(out);
  }
  return written;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  generate(GENERATED_DIR);
}
