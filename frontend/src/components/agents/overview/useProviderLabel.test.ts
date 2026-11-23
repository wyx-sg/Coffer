// src/components/agents/overview/useProviderLabel.test.ts — every agent type names its own login.
import { describe, expect, test } from "vitest";

import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";
import { AGENT_TYPES } from "@/lib/agents/routes";

describe("the Provider line of an agent on its own login", () => {
  test.each([
    ["en", en],
    ["zh", zh],
  ])("%s has words for every agent type", (_, locale) => {
    const builtin = locale.agents.overviewTab.model.builtin as Record<string, string>;
    for (const type of AGENT_TYPES) expect(builtin[type], type).toBeTruthy();
  });
});
