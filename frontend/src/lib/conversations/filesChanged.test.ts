// src/lib/conversations/filesChanged.test.ts
import { describe, expect, it } from "vitest";

import type { ContentBlock } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";
import { filesChanged } from "./filesChanged";

const use = (id: string, tool_name: string, tool_input: Record<string, unknown>): ContentBlock =>
  contentBlock({ type: "tool_use", tool_use_id: id, tool_name, tool_input });

describe("filesChanged", () => {
  it("counts an Edit's lines and adds a Write as new lines", () => {
    const blocks = [
      use("1", "Edit", { file_path: "a.py", old_string: "x\ny", new_string: "x\ny\nz" }),
      use("2", "Write", { file_path: "b.py", content: "1\n2\n3\n" }),
      use("3", "Read", { file_path: "c.py" }),
    ];
    expect(filesChanged(blocks)).toEqual([
      { path: "a.py", added: 3, removed: 2 },
      { path: "b.py", added: 3, removed: 0 },
    ]);
  });

  it("sums repeated edits to one file into one row", () => {
    const blocks = [
      use("1", "Edit", { file_path: "a.py", old_string: "x", new_string: "y" }),
      use("2", "MultiEdit", {
        file_path: "a.py",
        edits: [{ old_string: "p", new_string: "q\nr" }],
      }),
    ];
    expect(filesChanged(blocks)).toEqual([{ path: "a.py", added: 3, removed: 2 }]);
  });

  it("reads Codex's file_change diffs", () => {
    const diff = "--- a/x\n+++ b/x\n@@ -1 +1,2 @@\n-old\n+new\n+more";
    const blocks = [use("1", "file_change", { changes: [{ path: "x", diff }] })];
    expect(filesChanged(blocks)).toEqual([{ path: "x", added: 2, removed: 1 }]);
  });

  it("leaves out a call whose result is an error", () => {
    const blocks: ContentBlock[] = [
      use("1", "Write", { file_path: "a.py", content: "x" }),
      contentBlock({ type: "tool_result", tool_use_id: "1", tool_name: "Write", error: "denied" }),
    ];
    expect(filesChanged(blocks)).toEqual([]);
  });
});
