// src/i18n/locales.test.ts — guards for keys the chat surfaces render.
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "vitest";

import en from "./locales/en.json";
import zh from "./locales/zh.json";

test("errors.INTERNAL_ERROR reads as a readable message in every locale, never a shrug", () => {
  for (const text of [en.errors.INTERNAL_ERROR, zh.errors.INTERNAL_ERROR]) {
    expect(text).not.toMatch(/unexpected error|INTERNAL_ERROR|意外错误/i);
  }
});

function flatKeys(obj: unknown, prefix = ""): string[] {
  if (obj === null || typeof obj !== "object") return [prefix];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    flatKeys(v, prefix ? `${prefix}.${k}` : k),
  );
}

test("en and zh are at exact key parity (every key in both)", () => {
  const enKeys = flatKeys(en).sort();
  const zhKeys = flatKeys(zh).sort();
  const onlyEn = enKeys.filter((k) => !zhKeys.includes(k));
  const onlyZh = zhKeys.filter((k) => !enKeys.includes(k));
  expect({ onlyEn, onlyZh }).toEqual({ onlyEn: [], onlyZh: [] });
});

// ---------------------------------------------------------------------------
// Every literal key in the source resolves.
//
// Parity above proves en and zh say the same things; it cannot prove either
// says what the code asks for. `KnowledgeCreateDialog` shipped calling
// `t("common.create")` against a key present in NEITHER locale, so the dialog
// rendered the literal string "common.create" — perfectly at parity, and
// wrong in both languages. i18next has no compile-time link between a key and
// the bundle, so this walks the source instead.
//
// Deliberately a regex and not a parser: only the `t("literal")` form is
// checked, which is the form that can be checked at all. Keys assembled at
// runtime (`t(`errors.${code}`)`, `t(variable)`) are invisible here and stay
// the business of the tests that own those surfaces.

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** i18next resolves a `{{count}}` key through a plural suffix, never the bare key. */
const PLURAL_SUFFIXES = ["", "_zero", "_one", "_two", "_few", "_many", "_other"];

function resolves(key: string): boolean {
  return PLURAL_SUFFIXES.some((suffix) => {
    let node: unknown = en;
    for (const part of (key + suffix).split(".")) {
      if (node === null || typeof node !== "object" || !(part in node)) return false;
      node = (node as Record<string, unknown>)[part];
    }
    return typeof node === "string";
  });
}

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // Generated clients hold no translations, and locale JSON is the answer,
      // not the question.
      if (entry.name === "generated" || entry.name === "locales") continue;
      sourceFiles(full, out);
    } else if (/\.tsx?$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Blanks comments, keeping byte offsets so reported line numbers stay true.
 * Prose quoting a key is documentation, not a call — a comment explaining why
 * a key was removed must not fail this test.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\/[^\n]*|\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
}

test('every literal t("…") key in src/ resolves in the locale bundle', () => {
  // `(?<![\w$.])` keeps `expect(`, `assert(` and `obj.t(` out; a lone `t("…")`
  // with no dot in it is a plain string argument to something else, not a key.
  const call = /(?<![\w$.])t\(\s*"([^"\n]+)"/g;
  const unresolved: string[] = [];

  for (const file of sourceFiles(SRC)) {
    const source = withoutComments(fs.readFileSync(file, "utf-8"));
    for (const match of source.matchAll(call)) {
      const key = match[1];
      if (!key.includes(".") || resolves(key)) continue;
      const line = source.slice(0, match.index).split("\n").length;
      unresolved.push(`${path.relative(SRC, file)}:${line} → ${key}`);
    }
  }

  expect(unresolved).toEqual([]);
});

// ---------------------------------------------------------------------------
// The reverse: every key in the bundle is read somewhere.
//
// A key nothing references is a string a translator keeps maintaining for a
// screen that no longer exists (89 of them piled up once, including the copy of
// a "coming soon" placeholder the spec forbids). A key counts as read when its
// text appears in a non-test source file, or when it sits under a prefix the
// source builds at runtime (`t(`${K}.title.${state}`)`, `t("mcp.page.group." + g)`),
// or is a backend code the fixture lists.

function readSources(): string {
  const texts = sourceFiles(SRC)
    .filter((file) => !/\.test\.tsx?$/.test(file) && !file.includes(`${path.sep}test${path.sep}`))
    // Whole-line and JSDoc comments only: a cruder strip would read the `//` in
    // a URL or the `/*` in a glob as the start of a comment and blank real code.
    .map((file) =>
      fs
        .readFileSync(file, "utf-8")
        .replace(/^\s*\/\/.*$/gm, "")
        .replace(/\/\*\*[\s\S]*?\*\//g, ""),
    );
  texts.push(fs.readFileSync(path.join(SRC, "i18n", "backend-keys.fixture.json"), "utf-8"));
  return texts.join("\n");
}

/** The key prefixes the source assembles at runtime. */
function dynamicPrefixes(source: string): Set<string> {
  const prefixes = new Set<string>();
  // Several files each declare their own `const K = "…"`, so a name maps to every value it takes.
  const consts = new Map<string, string[]>();
  for (const m of source.matchAll(/const\s+(\w+)\s*=\s*"([\w.]+)"/g))
    consts.set(m[1], [...(consts.get(m[1]) ?? []), m[2]]);
  for (const m of source.matchAll(/([\w.]+)\.\$\{/g)) prefixes.add(m[1]);
  for (const m of source.matchAll(/\$\{(\w+)\}\./g)) {
    for (const value of consts.get(m[1]) ?? []) prefixes.add(value);
  }
  for (const m of source.matchAll(/"([\w.]+)\."\s*\+/g)) prefixes.add(m[1]);
  return prefixes;
}

test("every key in the en bundle is referenced by the source", () => {
  const source = readSources();
  const prefixes = [...dynamicPrefixes(source)];
  const unreferenced = flatKeys(en).filter((key) => {
    const bare = key.replace(/_(zero|one|two|few|many|other)$/, "");
    if (source.includes(bare)) return false;
    return !prefixes.some((prefix) => bare.startsWith(`${prefix}.`));
  });
  expect(unreferenced).toEqual([]);
});
