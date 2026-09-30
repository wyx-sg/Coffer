// frontend/src/lib/syncRoundToast.test.ts
//
// A finished round's toast says what actually happened: a round that stopped,
// was held, failed or is waiting to join is not a "success".
import { describe, expect, test } from "vitest";
import i18next from "@/i18n";
import type { TFunction } from "i18next";

import { makeRound } from "@/pages/sync/syncTestKit";
import { roundToast } from "./syncRoundToast";

const t = i18next.t.bind(i18next) as TFunction;

describe("roundToast", () => {
  test("a round that moved files is a success naming both directions", () => {
    const toast = roundToast(
      t,
      makeRound({ status: "pulled_and_pushed", pulled_files: 3, pushed_files: 2 }),
    );
    expect(toast.variant).toBe("success");
    expect(toast.message).toMatch(/3/);
    expect(toast.message).toMatch(/2/);
  });

  test.each(["stopped", "held", "waiting_on_edit", "join_required"] as const)(
    "%s asks for an answer rather than reporting success",
    (status) => {
      const toast = roundToast(t, makeRound({ status }));
      expect(toast.variant).toBe("info");
      expect(toast.message).not.toMatch(/^sync\./);
    },
  );

  test("a failed round carries git's own words", () => {
    const toast = roundToast(t, makeRound({ status: "auth_failed", detail: "HTTP 403" }));
    expect(toast.variant).toBe("error");
    expect(toast.message).toBe("HTTP 403");
  });
});
