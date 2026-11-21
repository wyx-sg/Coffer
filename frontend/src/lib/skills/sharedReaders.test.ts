import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import type { AgentTypeOut } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";
import { sharedFolders, useSharedReadersNote } from "@/lib/skills/sharedReaders";
import "@/i18n";

const types = vi.hoisted(() => ({ data: [] as unknown[] }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgentTypes: () => types }));

const row = (display_name: string, dirs: string[], uid: string | null = display_name) =>
  ({ display_name, uid, skill_dirs_read: dirs }) as unknown as AgentTypeOut;

const CLAUDE = "/h/.claude/skills";
const AGENTS = "/h/.agents/skills";

describe("sharedFolders", () => {
  it("names the agents that read one delivered folder, and the ones that also read another's", () => {
    const types = [
      row("Claude Code", [CLAUDE]),
      row("Codex", [AGENTS]),
      row("Antigravity", ["/h/.gemini/config/skills"]),
      row("Cursor", [AGENTS, CLAUDE]),
      row("OpenCode", [AGENTS, CLAUDE]),
    ];
    expect(sharedFolders(types)).toEqual([
      { delivered: ["Claude Code"], alsoReading: ["Cursor", "OpenCode"] },
      { delivered: ["Codex", "Cursor", "OpenCode"], alsoReading: [] },
    ]);
  });

  it("says nothing when every added agent reads a folder of its own", () => {
    const types = [
      row("Claude Code", [CLAUDE]),
      row("Codex", [AGENTS]),
      row("Cursor", [AGENTS, CLAUDE], null),
    ];
    expect(sharedFolders(types)).toEqual([]);
  });
});

acceptance("skill-manager", "the reach panel names who else sees a skill", () => {
  types.data = [
    row("Claude Code", [CLAUDE]),
    row("Codex", [AGENTS]),
    row("Cursor", [AGENTS, CLAUDE]),
    row("OpenCode", [AGENTS, CLAUDE]),
  ];
  const { result } = renderHook(() => useSharedReadersNote());
  expect(result.current).toBe(
    "A skill that reaches Claude Code is also seen by Cursor and OpenCode, which read its skills folder. " +
      "Codex, Cursor, and OpenCode read one skills folder, so a skill that reaches one of them reaches them all.",
  );
});
