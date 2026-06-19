// frontend/src/lib/hooks/useConfigEditorState.test.ts
// The config viewer hides config entries that don't exist on disk yet — a
// single file the agent hasn't created, or an empty/absent directory — rather
// than showing them dimmed. visibleConfigFiles is the pure filter behind that.
import { describe, expect, test } from "vitest";

import type { ConfigFileInfo } from "@/lib/api/agents";
import { visibleConfigFiles } from "./useConfigEditorState";

const file = (over: Partial<ConfigFileInfo>): ConfigFileInfo => ({
  key: "k",
  display_name: "K",
  path: "/p",
  format: "json",
  exists: true,
  size: null,
  modified_at: null,
  ...over,
});

describe("visibleConfigFiles", () => {
  test("hides single files that have not been created yet", () => {
    const out = visibleConfigFiles([
      file({ key: "settings", exists: true }),
      file({ key: "instructions", exists: false }),
    ]);
    expect(out.map((f) => f.key)).toEqual(["settings"]);
  });

  test("hides empty or absent directories, keeps directories with files", () => {
    const out = visibleConfigFiles([
      file({ key: "subagents", kind: "directory", exists: true, files: [] }),
      file({ key: "agents", kind: "directory", exists: false, files: null }),
      file({
        key: "commands",
        kind: "directory",
        exists: true,
        files: [{ relpath: "a.md", size: 1, modified_at: "2026-06-19T00:00:00Z" }],
      }),
    ]);
    expect(out.map((f) => f.key)).toEqual(["commands"]);
  });
});
