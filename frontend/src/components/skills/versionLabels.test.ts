// frontend/src/components/skills/versionLabels.test.ts — how a skill's History words a version.
import { describe, expect, test } from "vitest";
import i18n from "i18next";

import type { VaultVersionOut } from "@/lib/api/vault";
import { relPath, sourceIcon, versionNote, versionTitle } from "./versionLabels";
import "@/i18n";

const t = i18n.t.bind(i18n);
const FOLDER = "skills/deep-research/";

function v(over: Partial<VaultVersionOut>): VaultVersionOut {
  return {
    version: "a".repeat(40),
    time: "2026-09-27T18:20:00Z",
    writer: "user",
    display_writer: "user",
    actor: null,
    machine: null,
    summary: "Edit",
    operation: "edit",
    restored_from: null,
    removed: false,
    paths: [{ path: `${FOLDER}SKILL.md`, status: "modified", added: 1, removed: 1 }],
    ...over,
  };
}

describe("versionTitle", () => {
  const all = [v({ version: "b".repeat(40), time: "2026-09-20T10:01:00Z" })];

  test("says what was done to the one file a version touched", () => {
    expect(versionTitle(t, v({}), FOLDER, all, "en")).toBe("Edited SKILL.md");
    expect(versionTitle(t, v({ display_writer: "disk" }), FOLDER, all, "en")).toBe(
      "Changed SKILL.md",
    );
    expect(
      versionTitle(
        t,
        v({ paths: [{ path: `${FOLDER}scripts/a.py`, status: "added", added: 3, removed: 0 }] }),
        FOLDER,
        all,
        "en",
      ),
    ).toBe("Added scripts/a.py");
    expect(
      versionTitle(
        t,
        v({ paths: [{ path: `${FOLDER}old.md`, status: "removed", added: 0, removed: 3 }] }),
        FOLDER,
        all,
        "en",
      ),
    ).toBe("Removed old.md");
  });

  test("a restore names the day of the version it put back", () => {
    expect(versionTitle(t, v({ restored_from: "b".repeat(40) }), FOLDER, all, "en")).toBe(
      "Restored the version of Sep 20",
    );
    expect(versionTitle(t, v({ restored_from: "c".repeat(40) }), FOLDER, all, "en")).toBe(
      "Restored version ccccccc",
    );
  });

  test("several files are counted; none falls back to the commit's summary", () => {
    const two = [
      { path: `${FOLDER}a`, status: "modified", added: 1, removed: 0 },
      { path: `${FOLDER}b`, status: "modified", added: 1, removed: 0 },
    ];
    expect(versionTitle(t, v({ paths: two }), FOLDER, all, "en")).toBe("Changed 2 files");
    expect(
      versionTitle(t, v({ paths: [], summary: "History starts here" }), FOLDER, all, "en"),
    ).toBe("History starts here");
  });
});

describe("versionNote", () => {
  test("names who did it, and the current one says so", () => {
    expect(versionNote(t, v({}), FOLDER, [], true, "en", "")).toBe(
      "You edited SKILL.md in Coffer’s editor. This is the current version.",
    );
    expect(versionNote(t, v({ display_writer: "disk" }), FOLDER, [], false, "en", "")).toBe(
      "You changed SKILL.md in your own editor; Coffer kept it as a version.",
    );
    expect(
      versionNote(
        t,
        v({ display_writer: "agent:claude_code" }),
        FOLDER,
        [],
        false,
        "en",
        "Claude Code",
      ),
    ).toBe("Claude Code changed this skill’s files through Coffer.");
  });
});

describe("relPath and sourceIcon", () => {
  test("a path is relative to the skill's folder", () => {
    expect(relPath(FOLDER, `${FOLDER}scripts/a.py`)).toBe("scripts/a.py");
    expect(relPath(FOLDER, "other/x")).toBe("other/x");
  });

  test("each source has its own mark, and sync is Git's", () => {
    expect(sourceIcon("user")).toBe(sourceIcon("disk"));
    expect(sourceIcon("sync")).not.toBe(sourceIcon("user"));
    expect(sourceIcon("daemon")).not.toBe(sourceIcon("user"));
    expect(sourceIcon("agent:codex")).not.toBe(sourceIcon("user"));
  });
});
