// frontend/scripts/codegen.mjs — `npm run codegen`.
//
// Generates one TypeScript module per OpenAPI contract under
// `specs/<spec>/contracts/api.openapi.yaml` into
// `src/lib/api/generated/<spec>.ts`, through the openapi-typescript CLI so the
// output (and its "auto-generated" header the file-size gate keys on) is
// byte-identical to what the CLI would write by hand.
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
 * Every contract the frontend consumes, by spec folder name. The generated
 * module is `generated/<name>.ts`.
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

export function contractPath(name) {
  return path.join(REPO_ROOT, "specs", name, "contracts", "api.openapi.yaml");
}

/** Generate every contract into `outDir`, returning the written file paths. */
export function generate(outDir, { quiet = false } = {}) {
  mkdirSync(outDir, { recursive: true });
  const cli = path.join(FRONTEND_ROOT, "node_modules", "openapi-typescript", "bin", "cli.js");
  const written = [];
  for (const name of CONTRACTS) {
    const out = path.join(outDir, `${name}.ts`);
    execFileSync(process.execPath, [cli, contractPath(name), "-o", out], {
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
