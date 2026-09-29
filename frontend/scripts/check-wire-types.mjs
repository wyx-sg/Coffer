// frontend/scripts/check-wire-types.mjs — part of `npm run codegen:check`.
//
// No wire type is written by hand (Principles, "II. Spec-as-Truth" → Contract
// direction): the backend's Pydantic models generate each capability's
// contract, and the contract generates `src/lib/api/generated/`. A shape
// declared by hand in `src/lib/api/` is a second description of the wire that
// nothing compares with the first, so this gate refuses one.
//
// What it flags, in every non-test module directly under `src/lib/api/`:
//   - an exported `interface`;
//   - an exported `type` whose definition spells an object shape (`{ … }`)
//     anywhere in it, rather than naming generated schemas and deriving from
//     them (`components["schemas"]["X"]`, `Pick<…>`, `X["field"]`, unions of
//     those, string-literal unions).
//
// A declaration that never crosses the wire (request options a function
// takes, a view the UI derives) is marked with a `@ui-only` JSDoc tag on the
// declaration, with a word on why. The hand-written wire types that predate
// the generator are listed in `wire-types-allowlist.json`; the gate fails on
// an entry that no longer exists too, so the list only ever shrinks.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(here, "..");
const API_DIR = path.join(FRONTEND_ROOT, "src", "lib", "api");
const ALLOWLIST = path.join(here, "wire-types-allowlist.json");

function modules() {
  return readdirSync(API_DIR, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".ts") && !e.name.endsWith(".test.ts"))
    .map((e) => e.name)
    .sort();
}

function isExported(node) {
  return (ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export) !== 0;
}

function isUiOnly(node) {
  return ts.getJSDocTags(node).some((tag) => tag.tagName.text === "ui-only");
}

function spellsAShape(typeNode) {
  let found = false;
  const visit = (n) => {
    if (found) return;
    if (ts.isTypeLiteralNode(n) || ts.isMappedTypeNode(n)) {
      found = true;
      return;
    }
    ts.forEachChild(n, visit);
  };
  visit(typeNode);
  return found;
}

/** `file:Name` for every hand-written exported shape in `file`. */
function handWritten(file) {
  const text = readFileSync(path.join(API_DIR, file), "utf8");
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const out = [];
  for (const node of source.statements) {
    if (!isExported(node) || isUiOnly(node)) continue;
    if (ts.isInterfaceDeclaration(node)) out.push(`${file}:${node.name.text}`);
    else if (ts.isTypeAliasDeclaration(node) && spellsAShape(node.type)) {
      out.push(`${file}:${node.name.text}`);
    }
  }
  return out;
}

export function checkWireTypes() {
  const allowed = new Set(JSON.parse(readFileSync(ALLOWLIST, "utf8")).entries);
  const found = new Set(modules().flatMap(handWritten));
  const problems = [];
  for (const entry of [...found].sort()) {
    if (!allowed.has(entry)) {
      problems.push(
        `${entry} is a hand-written wire type — alias the generated schema ` +
          `(components["schemas"]["…"]) instead, fixing the backend model if the ` +
          `contract is not what the wire carries; mark it @ui-only if it never crosses the wire`,
      );
    }
  }
  for (const entry of [...allowed].sort()) {
    if (!found.has(entry)) {
      problems.push(`${entry} is on wire-types-allowlist.json but no longer hand-written — delete the entry`);
    }
  }
  return { problems, allowed: allowed.size };
}
