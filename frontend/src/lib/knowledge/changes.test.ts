// frontend/src/lib/knowledge/changes.test.ts — how the Knowledge page words, filters and groups changes.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import i18n from "@/i18n";
import type { ChangeOut } from "@/lib/api/knowledge";

import {
  agentLabel,
  changeSentence,
  dayKey,
  groupByDay,
  authorKey,
  authorOptions,
  matchesAuthor,
  undoneVersions,
  withinDays,
  writerLabel,
} from "./changes";
import { changePath, collectionOfPath, collectionPath, pathInCollection } from "./routes";
import { curatingLabel, describeItem } from "./text";

const t = i18n.getFixedT("en") as TFunction;

function change(over: Partial<ChangeOut>): ChangeOut {
  return {
    version: "v1",
    time: "2026-09-30T10:00:00Z",
    writer: "user",
    operation: "save",
    summary: "Edit x",
    actor: "user",
    agent: null,
    collections: ["c"],
    item: null,
    status: null,
    restored_from: null,
    undoes: null,
    documents: [{ path: "c/dir/doc.md", status: "modified", added: 1, removed: 1 }],
    ...over,
  };
}

describe("wording", () => {
  test("names writers and agents in words", () => {
    expect(writerLabel(t, change({}))).toBe("You");
    expect(writerLabel(t, change({ writer: "curation" }))).toBe("Curation");
    expect(writerLabel(t, change({ writer: "agent", agent: "claude-code" }))).toBe("Claude Code");
    expect(agentLabel(t, "codex")).toBe("Codex");
    expect(agentLabel(t, "user")).toBe("You");
    expect(agentLabel(t, "agent")).toBe("An agent");
  });

  test("words a change from its fields, the document without its collection", () => {
    expect(changeSentence(t, change({}))).toBe("edited dir/doc.md");
    expect(
      changeSentence(t, change({ writer: "curation", operation: "pass", agent: "codex" })),
    ).toBe("curated Codex's item into dir/doc.md");
    expect(changeSentence(t, change({ operation: "mystery", summary: "Raw subject" }))).toBe(
      "Raw subject",
    );
  });

  test("never says merge for curation", () => {
    const sentence = changeSentence(t, change({ writer: "curation", operation: "pass" }));
    expect(sentence).not.toMatch(/merg/i);
  });
});

describe("filters and grouping", () => {
  test("the Author filter names each person, agent and Curation once", () => {
    const mine = change({});
    const pass = change({ writer: "curation", operation: "pass", agent: "codex" });
    const codex = change({ writer: "agent", agent: "codex" });
    const claude = change({ writer: "agent", agent: "claude-code" });
    const all = [pass, claude, mine, codex, pass];
    expect(authorKey(pass)).toBe("curation");
    expect(authorKey(codex)).toBe("agent:codex");
    expect(all.filter((c) => matchesAuthor(c, "agent:codex"))).toEqual([codex]);
    expect(all.filter((c) => matchesAuthor(c, "user"))).toEqual([mine]);
    expect(all.filter((c) => matchesAuthor(c, "any"))).toHaveLength(5);
    expect(authorOptions(t, all)).toEqual([
      { value: "user", label: "You" },
      { value: "agent:claude-code", label: "Claude Code" },
      { value: "agent:codex", label: "Codex" },
      { value: "curation", label: "Curation" },
    ]);
  });

  test("groups by day under today, yesterday and a date", () => {
    const now = new Date(2026, 8, 30, 12);
    const at = (d: Date) => change({ time: d.toISOString() });
    const groups = groupByDay(
      [at(new Date(2026, 8, 30, 9)), at(new Date(2026, 8, 29, 9)), at(new Date(2026, 8, 20, 9))],
      now,
    );
    expect(groups.map(([day]) => day)).toEqual(["today", "yesterday", "2026-09-20"]);
    expect(dayKey(new Date(2026, 8, 30, 1).toISOString(), now)).toBe("today");
  });

  test("the last seven days, and the passes a later change undid", () => {
    const now = Date.parse("2026-09-30T10:00:00Z");
    expect(withinDays("2026-09-24T10:00:00Z", 7, now)).toBe(true);
    expect(withinDays("2026-09-22T10:00:00Z", 7, now)).toBe(false);
    expect(undoneVersions([change({ undoes: "p1" }), change({})])).toEqual(new Set(["p1"]));
  });
});

describe("addresses and derived text", () => {
  test("builds the page's addresses", () => {
    expect(collectionPath("kn-1")).toBe("/knowledge/kn-1");
    expect(collectionPath("kn-1", "history", "c/a b.md")).toBe(
      "/knowledge/kn-1/history?file=c%2Fa%20b.md",
    );
    expect(changePath("abc")).toBe("/knowledge/changes/abc");
    expect(collectionOfPath("c/dir/doc.md")).toBe("c");
    expect(pathInCollection("c/dir/doc.md")).toBe("dir/doc.md");
  });

  test("reads a Curate now run's progress, counting the pass in flight from one", () => {
    const run = { kind: "knowledge", name: "kn-1", started_at: "", done: 0, total: 2 };
    expect(curatingLabel(t, run)).toBe("Curating · 1 of 2");
    expect(curatingLabel(t, { ...run, done: 5 })).toBe("Curating · 2 of 2");
    expect(curatingLabel(t, null)).toBe("Curating…");
  });

  test("describes an added item by its first sentence, else its title", () => {
    expect(describeItem("T", "# Heading\n\nFirst one. Second one.")).toBe("First one.");
    expect(describeItem("Only a title", "")).toBe("Only a title");
  });
});
