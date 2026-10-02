// frontend/scripts/check-wire-types.mjs — part of `npm run codegen:check`.
//
// No wire type is written by hand (Principles, "II. Spec-as-Truth" → Contract
// direction): the backend's Pydantic models generate each capability's
// contract, and the contract generates `src/lib/api/generated/`. A shape
// declared by hand in `src/lib/api/` is a second description of the wire that
// nothing compares with the first, so this gate refuses one.
//
// What it flags, in every non-test module directly under `src/lib/api/` and
// anywhere under `src/lib/hooks/`:
//   - an exported `interface`;
//   - an exported `type` whose definition spells an object shape (`{ … }`)
//     anywhere in it, rather than naming generated schemas and deriving from
//     them (`components["schemas"]["X"]`, `Pick<…>`, `X["field"]`, unions of
//     those, string-literal unions);
//   - a call to `unwrap` / `unwrapOptional` / `unwrapVoid` whose type argument
//     spells an object shape: the response type comes from the typed client,
//     so a literal there is a second, unchecked description of the wire.
//
// A declaration that never crosses the wire (request options a function
// takes, a view the UI derives) is marked with a `@ui-only` JSDoc tag on the
// declaration, with a word on why. There is no allow-list: `@ui-only` is the
// only exemption.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(here, "..");
const API_DIR = path.join(FRONTEND_ROOT, "src", "lib", "api");
const LIB_DIR = path.join(FRONTEND_ROOT, "src", "lib");
const HOOKS_DIR = path.join(LIB_DIR, "hooks");

const isSource = (name) => /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name);

/** Paths relative to `src/lib/`: `api/*.ts` (not recursive: `generated/` is output) and `hooks/**`. */
function modules() {
  const out = readdirSync(API_DIR, { withFileTypes: true })
    .filter((e) => e.isFile() && isSource(e.name))
    .map((e) => `api/${e.name}`);
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (e.isFile() && isSource(e.name)) out.push(path.relative(LIB_DIR, full));
    }
  };
  walk(HOOKS_DIR);
  return out.sort();
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

/** `file:Name` for every hand-written exported shape in `file`, and `file:unwrap<{…}>` for literal type arguments. */
function handWritten(file) {
  const text = readFileSync(path.join(LIB_DIR, file), "utf8");
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const out = [];
  for (const node of source.statements) {
    if (!isExported(node) || isUiOnly(node)) continue;
    if (ts.isInterfaceDeclaration(node)) out.push(`${file}:${node.name.text}`);
    else if (ts.isTypeAliasDeclaration(node) && spellsAShape(node.type)) {
      out.push(`${file}:${node.name.text}`);
    }
  }
  const visit = (n) => {
    if (
      ts.isCallExpression(n) &&
      ts.isIdentifier(n.expression) &&
      /^unwrap(Optional|Void)?$/.test(n.expression.text) &&
      n.typeArguments?.some(spellsAShape)
    ) {
      const { line } = source.getLineAndCharacterOfPosition(n.getStart());
      out.push(`${file}:${line + 1} ${n.expression.text}<{…}>`);
    }
    ts.forEachChild(n, visit);
  };
  visit(source);
  return out;
}

export function checkWireTypes() {
  const problems = [];
  const files = modules();
  for (const entry of files.flatMap(handWritten)) {
    problems.push(
      entry.includes("<{…}>")
        ? `${entry} spells a wire shape by hand — drop the type argument (the typed client infers it) or alias the generated schema`
        : `${entry} is a hand-written wire type — alias the generated schema ` +
            `(components["schemas"]["…"]) instead, fixing the backend model if the ` +
            `contract is not what the wire carries; mark it @ui-only if it never crosses the wire`,
    );
  }
  return { problems, scanned: files.length };
}
