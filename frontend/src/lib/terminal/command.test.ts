import { describe, expect, test } from "vitest";

import { resumeCommand, shellQuote } from "./command";

describe("shellQuote", () => {
  test("wraps in single quotes and escapes a quote inside", () => {
    expect(shellQuote("/work/api")).toBe("'/work/api'");
    expect(shellQuote("/work/it's here")).toBe(`'/work/it'\\''s here'`);
  });

  test("keeps spaces and shell metacharacters inert", () => {
    expect(shellQuote("/a b/$(whoami);`id`")).toBe("'/a b/$(whoami);`id`'");
  });
});

describe("resumeCommand", () => {
  test("Claude Code resumes with --resume in the session's directory", () => {
    expect(resumeCommand("claude_code", "/work/api", "abc-123")).toBe(
      "cd '/work/api' && claude --resume abc-123",
    );
  });

  test("Codex resumes with the resume subcommand", () => {
    expect(resumeCommand("codex", "/work/api", "abc-123")).toBe(
      "cd '/work/api' && codex resume abc-123",
    );
  });

  test("a directory with a quote is escaped", () => {
    expect(resumeCommand("codex", "/work/it's", "s1")).toBe(
      `cd '/work/it'\\''s' && codex resume s1`,
    );
  });

  test("no directory leaves just the resume command", () => {
    expect(resumeCommand("claude_code", null, "s1")).toBe("claude --resume s1");
  });

  test("an id outside the safe set is quoted", () => {
    expect(resumeCommand("codex", null, "a b")).toBe("codex resume 'a b'");
  });
});
