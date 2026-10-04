// frontend/src/lib/skills/attention.test.ts
// What a skill needs the reader to know: the problems that file it under
// "Needs attention", tint its header pill —
// and the update that is waiting, which is none of those.
import { describe, expect, test } from "vitest";

import { cli, JQ_MISSING, UV_READY } from "@/test/cliFixtures";
import { BUILTIN_SKILL, makeSkill } from "@/test/skillsPageKit";
import {
  skillAttention,
  skillProblems,
  skillsNeedingAttention,
  skillStatus,
} from "@/lib/skills/attention";
import { skillGroup } from "@/lib/skills/groups";

const GITHUB_OFF = {
  name: "github",
  uid: "t-1",
  kind: "mcp_server" as const,
  status: "off" as const,
  why: null,
};

describe("skillAttention", () => {
  test("a tool it calls that is off or failing is an item, a healthy one is not", () => {
    const skill = makeSkill({
      requires_tools: [
        GITHUB_OFF,
        { ...GITHUB_OFF, uid: "t-2", name: "linear", status: "healthy" },
      ],
    });
    const items = skillAttention(skill, [], undefined);
    expect(items).toEqual([{ kind: "toolOff", tools: [GITHUB_OFF] }]);
  });

  test("most urgent first: master gone, then commands, then tools, then secrets", () => {
    const skill = makeSkill({
      master_missing: true,
      requires: [{ command: "jq", min_version: null }],
      requires_tools: [GITHUB_OFF],
      requires_secrets: [{ name: "TOKEN", is_set: false }],
    });
    const kinds = skillAttention(skill, [JQ_MISSING], undefined).map((i) => i.kind);
    expect(kinds).toEqual(["masterMissing", "requires", "toolOff", "secrets"]);
  });
});

describe("problems and the count", () => {
  const clean = makeSkill({
    uid: "a",
    name: "clean",
    requires: [{ command: "uv", min_version: null }],
  });
  const toolOff = makeSkill({ uid: "b", name: "tool-off", requires_tools: [GITHUB_OFF] });
  const updating = makeSkill({
    uid: "c",
    name: "updating",
    source_status: {
      checked_at: null,
      commits_ahead: 2,
      dismissed_commit: null,
      error: null,
      files_changed: 1,
      last_success_at: null,
      latest_commit: "f",
      update_available: true,
    },
  });

  test("a waiting update is not a problem", () => {
    expect(skillAttention(updating, [], undefined)).toHaveLength(1);
    expect(skillProblems(updating, [], undefined)).toEqual([]);
  });

  test("the built-in skill never needs attention", () => {
    const builtin = { ...BUILTIN_SKILL, master_missing: true };
    expect(skillProblems(builtin, [], undefined)).toEqual([]);
  });

  test("skillsNeedingAttention lists the skills with a problem — the library group", () => {
    const missing = makeSkill({
      uid: "d",
      name: "needs-jq",
      requires: [{ command: "jq", min_version: null }],
    });
    const found = skillsNeedingAttention(
      [clean, toolOff, updating, missing, BUILTIN_SKILL],
      [UV_READY, JQ_MISSING, cli({ command: "gh" })],
      undefined,
    );
    expect(found.map((s) => s.name)).toEqual(["tool-off", "needs-jq"]);
  });
});

describe("skillStatus", () => {
  test("names the header pill from the most urgent problem, else On or Off", () => {
    expect(skillStatus(makeSkill(), [])).toBe("inUse");
    expect(skillStatus(makeSkill({ enabled: false }), [])).toBe("off");
    const tool = makeSkill({ requires_tools: [GITHUB_OFF] });
    expect(skillStatus(tool, skillAttention(tool, [], undefined))).toBe("toolOff");
    const gone = makeSkill({ master_missing: true });
    expect(skillStatus(gone, skillAttention(gone, [], undefined))).toBe("masterMissing");
    const jq = makeSkill({ requires: [{ command: "jq", min_version: null }] });
    expect(skillStatus(jq, skillAttention(jq, [JQ_MISSING], undefined))).toBe("commandMissing");
  });
});

describe("skillGroup", () => {
  test("Needs attention beats reach; Built-in beats everything; Off is disabled or limited to nobody", () => {
    expect(skillGroup(makeSkill(), true)).toBe("attention");
    expect(skillGroup(makeSkill(), false)).toBe("inUse");
    expect(skillGroup(makeSkill({ enabled: false }), false)).toBe("off");
    expect(skillGroup(makeSkill({ scope: { agents: [] } }), false)).toBe("off");
    expect(skillGroup(BUILTIN_SKILL, true)).toBe("builtin");
  });
});
