// src/lib/agents/rowState.test.ts — the one state an agent reads as.
import { describe, expect, test } from "vitest";

import { agentRowState, agentRowTone, isAddableState, isReachableState } from "./rowState";

describe("agentRowState", () => {
  test("a type not added reads by its detection state", () => {
    expect(agentRowState({ state: "missing", uid: null })).toBe("not_installed");
    expect(agentRowState({ state: "config_only", uid: null })).toBe("config_left_behind");
    expect(agentRowState({ state: "installed_never_run", uid: null })).toBe("never_run");
    expect(agentRowState({ state: "installed_active", uid: null })).toBe("not_added");
  });

  test("detection wins over the connection of an added agent whose program is gone", () => {
    expect(agentRowState({ state: "config_only", uid: "u" }, "connected")).toBe(
      "config_left_behind",
    );
    expect(agentRowState({ state: "missing", uid: "u" }, "connected")).toBe("not_found");
  });

  test("an added agent reads its switch, then its connection", () => {
    const row = { state: "installed_active" as const, uid: "u" };
    expect(agentRowState(row, "connected", false)).toBe("disabled");
    expect(agentRowState(row, undefined)).toBe("checking");
    expect(agentRowState(row, "connected")).toBe("connected");
    expect(agentRowState(row, "partial")).toBe("needs_repair");
    expect(agentRowState(row, "disconnected")).toBe("not_connected");
  });

  test("tones and predicates", () => {
    expect(agentRowTone("connected")).toBe("ok");
    expect(agentRowTone("needs_repair")).toBe("warn");
    expect(agentRowTone("not_found")).toBe("err");
    expect(agentRowTone("not_added")).toBe("off");
    expect(isAddableState("never_run")).toBe(true);
    expect(isAddableState("config_left_behind")).toBe(false);
    expect(isReachableState("connected")).toBe(true);
    expect(isReachableState("not_found")).toBe(false);
  });
});
