// frontend/src/lib/vault/versionLabels.test.ts — how a History tab words a
// version: its writer in a word and what it did, for a file and for a folder.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import i18n from "@/i18n";
import type { VaultVersionOut } from "@/lib/api/vault";

import { relPath, vaultWriterLabel, versionCounts, versionTitle } from "./versionLabels";

const t = i18n.getFixedT("en") as TFunction;

function v(paths: [string, string][], extra: Partial<VaultVersionOut> = {}): VaultVersionOut {
  return {
    version: "a".repeat(40),
    time: "2026-09-20T10:00:00Z",
    writer: "user",
    display_writer: "user",
    actor: null,
    machine: null,
    summary: "Saved",
    operation: "edit",
    restored_from: null,
    removed: false,
    paths: paths.map(([path, status]) => ({ path, status, added: 2, removed: 1 })),
    ...extra,
  };
}

describe("vaultWriterLabel", () => {
  test("names each writer in a word, and an agent by its product", () => {
    expect(vaultWriterLabel(t, "user")).toBe("You");
    expect(vaultWriterLabel(t, "disk")).toBe("Edited on disk");
    expect(vaultWriterLabel(t, "agent:claude-code")).toBe("Claude Code");
    expect(vaultWriterLabel(t, "agent")).toBe("An agent");
    expect(vaultWriterLabel(t, "daemon")).toBe("Coffer");
    expect(vaultWriterLabel(t, "curation")).toBe("Coffer");
    expect(vaultWriterLabel(t, "memory-sync")).toBe("Coffer");
    expect(vaultWriterLabel(t, "sync")).toBe("Sync");
  });
});

describe("versionTitle", () => {
  test("a file's version says what happened to the file", () => {
    const file = "knowledge/a.md";
    expect(versionTitle(t, v([[file, "added"]]), file, [], "en")).toBe("Created");
    expect(versionTitle(t, v([[file, "modified"]]), file, [], "en")).toBe("Edited");
    expect(versionTitle(t, v([[file, "removed"]]), file, [], "en")).toBe("Deleted");
  });

  test("a folder's version names the file, or counts them", () => {
    const base = "skills/pdf/";
    expect(versionTitle(t, v([["skills/pdf/x.py", "added"]]), base, [], "en")).toBe("Added x.py");
    const two = v([
      ["skills/pdf/SKILL.md", "modified"],
      ["skills/pdf/x.py", "removed"],
    ]);
    expect(versionTitle(t, two, base, [], "en")).toBe("Changed 2 files");
    expect(versionCounts(two)).toEqual({ added: 4, removed: 2 });
  });

  test("a restore names the version it put back", () => {
    const older = v([["skills/pdf/SKILL.md", "added"]], { version: "b".repeat(40) });
    const restore = v([["skills/pdf/SKILL.md", "modified"]], { restored_from: "b".repeat(40) });
    expect(versionTitle(t, restore, "skills/pdf/", [restore, older], "en")).toMatch(
      /^Restored the version of /,
    );
    expect(versionTitle(t, restore, "skills/pdf/", [restore], "en")).toBe(
      "Restored version bbbbbbb",
    );
  });

  test("relPath strips the folder only", () => {
    expect(relPath("skills/pdf/", "skills/pdf/a/b.md")).toBe("a/b.md");
    expect(relPath("knowledge/a.md", "knowledge/a.md")).toBe("knowledge/a.md");
  });
});
