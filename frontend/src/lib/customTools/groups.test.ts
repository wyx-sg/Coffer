// src/lib/customTools/groups.test.ts — which servers are groups, and how the list sections them.
import { describe, expect, test } from "vitest";

import { makeGroup, makeTool } from "@/components/custom-tools/testFixtures";
import { isCustomToolGroup, sectionGroups } from "./groups";

describe("isCustomToolGroup", () => {
  test("is true only for the http_api transport", () => {
    expect(isCustomToolGroup({ config: { transport: { type: "http_api" } } })).toBe(true);
    expect(isCustomToolGroup({ config: { transport: { type: "stdio" } } })).toBe(false);
    expect(isCustomToolGroup({ config: {} })).toBe(false);
    expect(isCustomToolGroup({})).toBe(false);
  });
});

describe("sectionGroups", () => {
  const groups = [
    makeGroup({ name: "zeta", health: "idle" }),
    makeGroup({ name: "alpha", health: "healthy" }),
    makeGroup({ name: "grafana", health: "attention" }),
    makeGroup({ name: "deploy", health: "failing" }),
    makeGroup({ name: "pager", health: "off", enabled: false }),
  ];

  test("puts failing before attention, healthy before idle, off last", () => {
    expect(sectionGroups(groups, "").map((s) => [s.section, s.groups.map((g) => g.name)])).toEqual([
      ["attention", ["deploy", "grafana"]],
      ["healthy", ["alpha", "zeta"]],
      ["off", ["pager"]],
    ]);
  });

  test("filters by name, host or tool name and drops empty sections", () => {
    const withTool = [
      ...groups,
      makeGroup({ name: "billing", tools: [makeTool({ name: "refund_charge" })] }),
    ];
    expect(sectionGroups(withTool, "refund").map((s) => s.groups.map((g) => g.name))).toEqual([
      ["billing"],
    ]);
    expect(sectionGroups(withTool, "pager.internal")[0].section).toBe("off");
  });
});
