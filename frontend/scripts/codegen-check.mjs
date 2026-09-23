// frontend/scripts/codegen-check.mjs — `npm run codegen:check`.
//
// Regenerates every contract into a temp dir and diffs it against
// `src/lib/api/generated/`. Exits 1 naming each file that drifted — a contract
// edited without `npm run codegen`, or a generated file edited by hand — so
// `npm run lint` (and therefore CI) catches it without a workflow change.
//
// Everything here works in spec ids, which may be nested paths
// (`channels/telegram` → `generated/channels/telegram.ts`), so the walk below
// is recursive and comparisons are made on forward-slash relative paths.
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { CONTRACTS, GENERATED_DIR, generate, generatedPath } from "./codegen.mjs";

/** Every file under `dir`, at any depth, as forward-slash relative paths. */
function walk(dir, prefix = "") {
  if (!existsSync(dir)) return [];
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out.push(...walk(path.join(dir, entry.name), rel));
    else out.push(rel);
  }
  return out;
}

const tmp = mkdtempSync(path.join(os.tmpdir(), "coffer-codegen-"));
const drifted = [];
try {
  generate(tmp, { quiet: true });

  for (const id of CONTRACTS) {
    const rel = `${id}.ts`;
    const committed = generatedPath(GENERATED_DIR, id);
    if (!existsSync(committed)) {
      drifted.push(`${rel} (missing — run \`npm run codegen\`)`);
      continue;
    }
    const fresh = readFileSync(generatedPath(tmp, id), "utf8");
    if (readFileSync(committed, "utf8") !== fresh) {
      drifted.push(`${rel} (out of date — run \`npm run codegen\`)`);
    }
  }

  // A file in the generated dir that no contract produces is drift too: it
  // would otherwise survive forever as an orphan nothing regenerates. The walk
  // is recursive so a leftover under a renamed parent spec is caught as well.
  const expected = new Set(CONTRACTS.map((id) => `${id}.ts`));
  for (const rel of walk(GENERATED_DIR)) {
    if (!expected.has(rel)) drifted.push(`${rel} (no contract generates it — delete it)`);
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

if (drifted.length > 0) {
  console.error("codegen:check — src/lib/api/generated/ is out of step with openspec/specs/*/contracts:");
  for (const line of drifted) console.error(`  - ${line}`);
  process.exit(1);
}
console.log(`codegen:check — ${CONTRACTS.length} generated modules match their contracts.`);
