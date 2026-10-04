// frontend/src/lib/skills/delivery.test.ts
// Where each agent's copy of a skill stands, derived from the skill's
// bindings, the agents' switches and (after Check again) the drift report.
import { describe, expect, test } from "vitest";

import { deliveryRows } from "@/lib/skills/delivery";
import { makeAgent, makeSkill } from "@/test/skillsPageKit";

const CC = makeAgent();
const CODEX = makeAgent({ uid: "ag-cx", name: "codex", type: "codex" });
describe("deliveryRows", () => {
  test("a binding is linked, or copied when the link fell back to a copy", () => {
    const skill = makeSkill({
      bindings: [
        {
          agent_uid: CC.uid,
          agent_name: CC.name,
          last_linked_at: null,
          last_link_path: "/l",
          link_mode: "junction",
        },
        {
          agent_uid: CODEX.uid,
          agent_name: CODEX.name,
          last_linked_at: null,
          last_link_path: "/c",
          link_mode: "copy_fallback",
        },
      ],
    });
    expect(deliveryRows(skill, [CC, CODEX], null).map((r) => r.delivery)).toEqual([
      { state: "linked", path: "/l" },
      { state: "copied", path: "/c" },
    ]);
  });

  test("without a binding the first reason that applies is given", () => {
    const off = makeSkill({ enabled: false, scope: { agents: [] } });
    expect(deliveryRows(off, [CC], null)[0].delivery).toEqual({
      state: "notDelivered",
      reason: "skillOff",
    });
    const scoped = makeSkill({ scope: { agents: [CC.uid] } });
    const rows = deliveryRows(scoped, [CC, CODEX], null);
    expect(rows.map((r) => r.delivery)).toEqual([
      { state: "notDelivered", reason: "pending" },
      { state: "notDelivered", reason: "outsideReach" },
    ]);
    expect(deliveryRows(makeSkill(), [CC], null)[0].delivery).toEqual({
      state: "notDelivered",
      reason: "pending",
    });
  });

  test("a drift finding for this skill and agent wins over the binding", () => {
    const skill = makeSkill({
      bindings: [
        {
          agent_uid: CC.uid,
          agent_name: CC.name,
          last_linked_at: null,
          last_link_path: "/l",
          link_mode: "symlink",
        },
      ],
    });
    const drift = [
      {
        skill_name: "other",
        agent_name: CC.name,
        kind: "missing_link" as const,
        target_path: "/x",
        handoff: null,
      },
      {
        skill_name: skill.name,
        agent_name: CC.name,
        kind: "missing_link" as const,
        target_path: "/l",
        handoff: null,
      },
    ];
    expect(deliveryRows(skill, [CC], drift)[0].delivery).toEqual({
      state: "drift",
      kind: "missing_link",
      path: "/l",
    });
  });
});
