// src/i18n/surfaceNames.test.ts — one surface, one name.
//
// A surface the user reaches from the sidebar must be called the same thing on
// the page it opens: a reader who clicks 「聊天」 and lands on a page titled
// 「对话」 has to wonder whether they arrived where they meant to. This compares
// every sidebar entry's label with its page's title key, in both locales.
//
// The sidebar's entries are read from lib/navigation.ts itself, so a new entry
// without a row in TITLE_KEY_BY_ROUTE fails here rather than slipping past.
// Settings is not an entry but carries the same one-name rule, so its footer
// row's label is checked against the modal's title too.
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

const SIDEBAR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../lib/navigation.ts");

/** Each sidebar route → the i18n key its page renders as the title. */
const TITLE_KEY_BY_ROUTE: Record<string, string> = {
  "/": "overview.title",
  "/agents": "agents.title",
  "/model-providers": "providers.title",
  "/conversations": "conversations.title",
  "/channels": "channels.title",
  "/mcp-servers": "resources.title",
  "/custom-tools": "customTools.title",
  "/skills": "skills.title",
  "/clis": "clis.title",
  "/knowledge": "knowledge.title",
  "/memory": "memory.title",
  "/secrets": "secrets.title",
  "/activity": "activity.title",
  "/sync": "sync.title",
};

/** The Settings footer row and the modal it opens. */
const SETTINGS_ROW = { to: "settings", labelKey: "nav.settings", titleKey: "settings.title" };

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
    expect(entries).toHaveLength(14);
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
        .concat({
          to: SETTINGS_ROW.to,
          sidebar: lookup(bundle, SETTINGS_ROW.labelKey),
          page: lookup(bundle, SETTINGS_ROW.titleKey),
        })
        .filter((row) => typeof row.sidebar !== "string" || row.sidebar !== row.page);
      expect(mismatches).toEqual([]);
    });
  }
});

// The scenario's AND: the zh group headings, and no zh string calls an agent "Agent".
acceptance("web-ui", "a surface carries one name in the sidebar and on its page", () => {
  const values: string[] = [];
  const walk = (node: unknown) => {
    if (typeof node === "string") values.push(node);
    else if (node && typeof node === "object") Object.values(node).forEach(walk);
  };
  walk(zh);
  // Backticked code (`coffer daemon start`) and the AgentSkills standard's name
  // are identifiers, not names for an agent.
  // Interpolation placeholders ({{agent}}) and paths (~/.agents) are not prose.
  const prose = values.map((v) =>
    v
      .replace(/`[^`]*`/g, "")
      .replace(/\{\{[^}]*\}\}/g, "")
      .replace(/~\/\.agents\S*/g, "")
      .replace(/AgentSkills/g, ""),
  );
  expect(prose.filter((v) => /\bagents?\b|代理(?!的调用)/i.test(v))).toEqual([]);
  expect(lookup(zh, "nav.agents")).toBe("智能体");
  expect(
    ["agents", "run", "capabilities", "context", "system"].map((g) => lookup(zh, `nav.group.${g}`)),
  ).toEqual(["智能体", "运行", "能力", "上下文", "系统"]);
});
