// src/i18n/locales.test.ts — guards for keys the chat surfaces render.
import { expect, test } from "vitest";

import en from "./locales/en.json";
import zh from "./locales/zh.json";

test("common.dismiss exists in every locale (turn-error banner button)", () => {
  expect(en.common.dismiss).toBeTruthy();
  expect(zh.common.dismiss).toBeTruthy();
});

test("en and zh expose the same common.* keys", () => {
  expect(Object.keys(zh.common).sort()).toEqual(Object.keys(en.common).sort());
});

function flatKeys(obj: unknown, prefix = ""): string[] {
  if (obj === null || typeof obj !== "object") return [prefix];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    flatKeys(v, prefix ? `${prefix}.${k}` : k),
  );
}

test("en and zh are at exact key parity (every key in both)", () => {
  const enKeys = flatKeys(en).sort();
  const zhKeys = flatKeys(zh).sort();
  const onlyEn = enKeys.filter((k) => !zhKeys.includes(k));
  const onlyZh = zhKeys.filter((k) => !enKeys.includes(k));
  expect({ onlyEn, onlyZh }).toEqual({ onlyEn: [], onlyZh: [] });
});
