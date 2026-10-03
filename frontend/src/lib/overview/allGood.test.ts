// src/lib/overview/allGood.test.ts — the calm card's sentence says only what the lists support.
import i18n from "i18next";
import { expect, test } from "vitest";

import { allGoodSummary } from "./allGood";

const t = i18n.t.bind(i18n);
const TAIL = "Anything that needs you shows up here.";

test("each area with something to report adds a clause, singular or plural", () => {
  expect(allGoodSummary(t, { agents: 2, servers: 12, vaultInSync: true })).toBe(
    `Both agents are connected, 12 servers are answering and your vault is in sync. ${TAIL}`,
  );
  expect(allGoodSummary(t, { agents: 1, servers: 1 })).toBe(
    `Your agent is connected and 1 server is answering. ${TAIL}`,
  );
  expect(allGoodSummary(t, { agents: 3 })).toBe(`All 3 agents are connected. ${TAIL}`);
});

test("an area with nothing to report is left out, and with none the card says only where problems show", () => {
  expect(allGoodSummary(t, { agents: 0, servers: 0, vaultInSync: false })).toBe(TAIL);
  expect(allGoodSummary(t, {})).toBe(TAIL);
  expect(allGoodSummary(t, { vaultInSync: true })).toBe(`Your vault is in sync. ${TAIL}`);
});
