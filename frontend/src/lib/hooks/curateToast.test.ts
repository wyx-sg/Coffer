import { describe, expect, test } from "vitest";

import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

import { curateToastKey } from "./curateToast";

describe("the message a finished curation pass leaves", () => {
  test("names the pass's status", () => {
    expect(curateToastKey({ status: "ok", gave_up: false })).toBe("knowledge.curate.status.ok");
    expect(curateToastKey({ status: "truncated", gave_up: false })).toBe(
      "knowledge.curate.status.truncated",
    );
  });

  test("a pass that gave up on its item does not promise another try", () => {
    const key = curateToastKey({ status: "truncated", gave_up: true });
    expect(key).toBe("knowledge.curate.status.truncatedGaveUp");
    for (const locale of [en, zh]) {
      const text = (locale as { knowledge: { curate: { status: Record<string, string> } } })
        .knowledge.curate.status.truncatedGaveUp;
      expect(text).toBeTruthy();
    }
    expect(en.knowledge.curate.status.truncatedGaveUp).not.toMatch(/tried again/i);
  });
});
