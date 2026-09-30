// frontend/src/components/memory/memoryAgents.test.ts — provenance reduced to agent names.
import { describe, expect, test } from "vitest";

import { agentTypeOfOrigin, learnedByLabels } from "./memoryAgents";

describe("learnedByLabels", () => {
  test("names each agent once, Claude Code first, whatever the spelling", () => {
    expect(
      learnedByLabels([{ agent: "codex" }, { agent: "claude-code" }, { agent: "claude_code" }]),
    ).toEqual(["Claude Code", "Codex"]);
  });

  test("an unknown resource name is shown as written, after the known ones", () => {
    expect(learnedByLabels([{ agent: "my-bot" }, { agent: "codex" }])).toEqual(["Codex", "my-bot"]);
  });

  test("no provenance, no names", () => {
    expect(learnedByLabels([])).toEqual([]);
    expect(agentTypeOfOrigin(" Claude-Code ")).toBe("claude_code");
  });
});
