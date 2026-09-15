// frontend/scripts/codegen-check.mjs — `npm run codegen:check`.
//
// Regenerates every contract into a temp dir and diffs it against
// `src/lib/api/generated/`. Exits 1 naming each file that drifted — a contract
// edited without `npm run codegen`, or a generated file edited by hand — so
// `npm run lint` (and therefore CI) catches it without a workflow change.
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { CONTRACTS, GENERATED_DIR, generate } from "./codegen.mjs";

const tmp = mkdtempSync(path.join(os.tmpdir(), "coffer-codegen-"));
const drifted = [];
try {
  generate(tmp, { quiet: true });

  for (const name of CONTRACTS) {
    const file = `${name}.ts`;
    const committed = path.join(GENERATED_DIR, file);
    if (!existsSync(committed)) {
      drifted.push(`${file} (missing — run \`npm run codegen\`)`);
      continue;
    }
    const fresh = readFileSync(path.join(tmp, file), "utf8");
    if (readFileSync(committed, "utf8") !== fresh) {
      drifted.push(`${file} (out of date — run \`npm run codegen\`)`);
    }
  }

  // A file in the generated dir that no contract produces is drift too: it
  // would otherwise survive forever as an orphan nothing regenerates.
  const expected = new Set(CONTRACTS.map((name) => `${name}.ts`));
  for (const file of existsSync(GENERATED_DIR) ? readdirSync(GENERATED_DIR) : []) {
    if (!expected.has(file)) drifted.push(`${file} (no contract generates it — delete it)`);
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

if (drifted.length > 0) {
  console.error("codegen:check — src/lib/api/generated/ is out of step with specs/*/contracts:");
  for (const line of drifted) console.error(`  - ${line}`);
  process.exit(1);
}
console.log(`codegen:check — ${CONTRACTS.length} generated modules match their contracts.`);
