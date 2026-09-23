// src/i18n/surfaceNames.test.ts — one surface, one name.
//
// A surface the user reaches from the sidebar must be called the same thing on
// the page it opens: a reader who clicks 「聊天」 and lands on a page titled
// 「对话」 has to wonder whether they arrived where they meant to. This compares
// every sidebar entry's label with its page's title key, in both locales.
//
// The sidebar's entries are read from SidebarNav.tsx itself, so a new entry
// without a row in TITLE_KEY_BY_ROUTE fails here rather than slipping past.
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";
import { acceptance } from "@/test/acceptance";

// The zh bundle is where the two names once diverged, so it carries the marker.
const acceptanceZh = (_title: string, fn: () => void) =>
  acceptance("web-ui", "a surface carries one name in the sidebar and on its page", fn);

import en from "./locales/en.json";
import zh from "./locales/zh.json";

const SIDEBAR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../components/SidebarNav.tsx",
);

/** Each sidebar route → the i18n key its page renders as the title. */
const TITLE_KEY_BY_ROUTE: Record<string, string> = {
  "/agents": "agents.title",
  "/chat": "chat.title",
  "/mcp-servers": "resources.title",
  "/skills": "skills.title",
  "/knowledge": "knowledge.title",
  "/memory": "memory.title",
  "/model-providers": "settings.connections.title",
  "/channels": "channels.title",
  "/activity": "activity.title",
  "/sync": "sync.title",
  "/settings": "settings.title",
};

function sidebarEntries(): { to: string; labelKey: string }[] {
  const src = fs.readFileSync(SIDEBAR, "utf8");
  return [...src.matchAll(/\{\s*to:\s*"([^"]+)",\s*labelKey:\s*"([^"]+)"/g)].map((m) => ({
    to: m[1],
    labelKey: m[2],
  }));
}

function lookup(bundle: unknown, key: string): unknown {
  return key
    .split(".")
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === "object" ? (node as Record<string, unknown>)[part] : undefined,
      bundle,
    );
}

describe("a surface carries one name in the sidebar and on its page", () => {
  const entries = sidebarEntries();

  test("every sidebar entry has a known page title", () => {
    expect(entries.length).toBeGreaterThan(0);
    expect(entries.map((e) => e.to).sort()).toEqual(Object.keys(TITLE_KEY_BY_ROUTE).sort());
  });

  for (const [name, bundle] of [
    ["en", en],
    ["zh", zh],
  ] as const) {
    const check = name === "zh" ? acceptanceZh : test;
    check(`${name}: each sidebar label equals its page title`, () => {
      const mismatches = entries
        .map(({ to, labelKey }) => ({
          to,
          sidebar: lookup(bundle, labelKey),
          page: lookup(bundle, TITLE_KEY_BY_ROUTE[to]),
        }))
        .filter((row) => typeof row.sidebar !== "string" || row.sidebar !== row.page);
      expect(mismatches).toEqual([]);
    });
  }
});
