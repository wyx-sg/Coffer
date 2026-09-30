// src/lib/overview/health.test.ts — a tile's status comes from the attention items of its kinds.
import { expect, test } from "vitest";

import type { AttentionItem } from "@/lib/hooks/useAttention";
import { AREAS, areaProblems, areaStatus, deliveredAgentCount, uidsWithProblems } from "./health";

const at = (kind: string, severity: AttentionItem["severity"], uid: string | null = null) =>
  ({ kind, severity, uid }) as AttentionItem;

test("errors outrank warnings; info counts as a warning; other kinds do not count", () => {
  const items = [at("mcp_server", "error"), at("mcp_server", "info"), at("skill", "error")];
  expect(areaStatus(areaProblems(items, ["mcp_server"]))).toEqual({ tone: "err", count: 1 });
  expect(areaStatus(areaProblems([at("agent", "info")], ["agent"]))).toEqual({
    tone: "warn",
    count: 1,
  });
  expect(areaStatus(areaProblems(items, ["channel"]))).toEqual({ tone: "ok", count: 0 });
});

test("the uids reported about a kind", () => {
  const items = [
    at("agent", "info", "a1"),
    at("agent", "warning", "a1"),
    at("skill", "error", "s"),
  ];
  expect([...uidsWithProblems(items, "agent")]).toEqual(["a1"]);
});

test("skills count the distinct agents they reach", () => {
  const b = (agent_uid: string) => ({ agent_uid });
  expect(deliveredAgentCount([{ bindings: [b("a"), b("b")] }, { bindings: [b("a")] }])).toBe(2);
});

test("every sidebar area but Overview, Conversations and Activity has a tile, in the board's order", () => {
  expect(AREAS.map((a) => a.to)).toEqual([
    "/agents",
    "/mcp-servers",
    "/skills",
    "/knowledge",
    "/memory",
    "/model-providers",
    "/channels",
    "/sync",
    "/custom-tools",
    "/clis",
    "/secrets",
    "/usage",
  ]);
});
