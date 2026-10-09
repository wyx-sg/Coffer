// frontend/src/lib/knowledge/changes.test.ts — how a knowledge writer and a time are worded, and the page's addresses.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import i18n from "@/i18n";
import type { ChangeOut } from "@/lib/api/knowledge";

import { agentLabel, dayKey, operationLabel, whenLabel, writerLabel } from "./changes";
import { collectionPath, legacyRedirect, pathInCollection } from "./routes";

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
    expect(writerLabel(t, change({ writer: "daemon" }))).toBe("Coffer");
  });

  test("says what a change did", () => {
    expect(operationLabel(t, change({ operation: "layout" }))).toBe("Filed into pages");
    expect(operationLabel(t, change({ operation: "pass" }))).toBe("Curated");
    expect(operationLabel(t, change({ operation: "unknown", summary: "Something" }))).toBe(
      "Something",
    );
  });

  test("words a time as today, yesterday or a date", () => {
    const now = new Date(2026, 8, 30, 12);
    expect(dayKey(new Date(2026, 8, 30, 1).toISOString(), now)).toBe("today");
    expect(dayKey(new Date(2026, 8, 29, 9).toISOString(), now)).toBe("yesterday");
    expect(dayKey(new Date(2026, 8, 20, 9).toISOString(), now)).toBe("2026-09-20");
    expect(whenLabel(t, new Date(2026, 8, 30, 9, 5).toISOString(), "en", now)).toBe("Today 09:05");
  });
});

describe("addresses", () => {
  test("builds the page's addresses", () => {
    expect(collectionPath("kn-1")).toBe("/knowledge/kn-1");
    expect(collectionPath("kn-1", "c/a b.md")).toBe("/knowledge/kn-1?file=c%2Fa%20b.md");
    expect(collectionPath("kn-1", "c/a.md", { history: true })).toBe(
      "/knowledge/kn-1?file=c%2Fa.md&history=1",
    );
    expect(pathInCollection("c/dir/doc.md")).toBe("dir/doc.md");
  });

  test("sends the old History tab address to the drawer, any other segment to the bare address", () => {
    expect(legacyRedirect("kn-1", "history", "?file=c%2Fa.md")).toBe(
      "/knowledge/kn-1?file=c%2Fa.md&history=1",
    );
    expect(legacyRedirect("kn-1", "changes", "?file=c%2Fa.md")).toBe(
      "/knowledge/kn-1?file=c%2Fa.md",
    );
    expect(legacyRedirect("kn-1", "history", "")).toBe("/knowledge/kn-1");
  });
});
