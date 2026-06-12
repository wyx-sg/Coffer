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
