// src/lib/themeTokens.test.ts — the token stylesheet defines every colour role
// for both themes and loads its fonts from the build, never from another host.
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect } from "vitest";

import { acceptance } from "@/test/acceptance";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const css = readFileSync(resolve(SRC, "index.css"), "utf-8");
const tailwind = readFileSync(resolve(SRC, "..", "tailwind.config.js"), "utf-8");

/** The body of the first `selector { … }` block (no nested braces inside). */
function block(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `${selector} block`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  return css.slice(open + 1, css.indexOf("}", open));
}

/** Colour roles: custom properties whose value is RGB channels or a colour. */
function colourRoles(body: string): Set<string> {
  const roles = new Set<string>();
  for (const [, name, value] of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    if (/^\d+ \d+ \d+$/.test(value.trim()) || /^rgba?\(/.test(value.trim())) roles.add(name);
  }
  return roles;
}

acceptance("web-ui", "every colour role is defined for both themes", () => {
  const light = colourRoles(block(":root"));
  const dark = colourRoles(block(':root[data-theme="dark"]'));
  // The find-in-preview highlights are the same yellow in both themes.
  const shared = new Set(["highlight", "highlight-active"]);
  const missing = [...light].filter((role) => !shared.has(role) && !dark.has(role));
  expect(light.size).toBeGreaterThan(24);
  expect(missing).toEqual([]);
});

acceptance("web-ui", "the interface fonts load from the app's own origin", () => {
  const sources = [...css.matchAll(/src:\s*url\("([^"]+)"\)/g)].map((m) => m[1]);
  expect(sources.length).toBeGreaterThan(0);
  for (const src of sources) {
    expect(src, src).not.toMatch(/^(https?:)?\/\//);
    expect(src).toMatch(/\.woff2$/);
    expect(existsSync(resolve(SRC, src)), src).toBe(true);
  }
  expect(css).not.toMatch(/@import\s+url\(\s*["']?https?:/);

  expect(tailwind).toMatch(/sans: \['"Figtree"'/);
  expect(tailwind).toMatch(/mono: \['"JetBrains Mono"'/);
  // 13px is the base: body text and the default body size both resolve to it.
  expect(tailwind).toMatch(/\bsm: \["13px"/);
  expect(css).toMatch(/body \{\s*@apply bg-surface font-sans text-sm/);
});
