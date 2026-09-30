// src/lib/conversations/toolSummary.test.ts
import { describe, expect, it } from "vitest";

import { toolSummary } from "./toolSummary";

describe("toolSummary", () => {
  it("names the file or command a call worked on", () => {
    expect(toolSummary({ file_path: "src/a.py", offset: 1 })).toBe("src/a.py");
    expect(toolSummary({ command: "uv run pytest -q" })).toBe("uv run pytest -q");
    expect(toolSummary({ pattern: "on_close", path: "src" })).toBe('src · "on_close"');
  });

  it("falls back to the first string argument, then to changed paths", () => {
    expect(toolSummary({ project: "coffer", since: "24h" })).toBe("coffer");
    expect(toolSummary({ changes: [{ path: "a" }, { path: "b" }] })).toBe("a, b");
    expect(toolSummary(null)).toBe("");
  });

  it("keeps a long argument to one short line", () => {
    const out = toolSummary({ command: `echo ${"x".repeat(300)}\nnext` });
    expect(out.length).toBeLessThanOrEqual(120);
    expect(out).not.toContain("\n");
  });
});
