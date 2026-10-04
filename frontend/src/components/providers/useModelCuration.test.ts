// src/components/providers/useModelCuration.test.ts — turning many models on or off at once.
//
// Empty `models` reads as "no restriction", so "all off" is refused when it
// would leave nothing on, and "off" on an unrestricted provider writes the
// whole explicit list minus the matched rows.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import type { Provider, ProviderModel } from "@/lib/api/providers";
import { useModelCuration } from "./useModelCuration";

const mutate = vi.fn();
vi.mock("@/lib/hooks/useProviders", () => ({
  useUpdateProvider: () => ({ mutate, isPending: false }),
}));

const m = (id: string, modality: ProviderModel["modality"] = "text"): ProviderModel => ({
  id,
  modality,
});
const provider = (models: ProviderModel[]) => ({ uid: "p1", models }) as unknown as Provider;
const hook = (models: ProviderModel[], fetched: ProviderModel[]) =>
  renderHook(() => useModelCuration(provider(models), fetched)).result.current;
const written = () => mutate.mock.calls[0][0].patch.models;

beforeEach(() => mutate.mockClear());

describe("setMany", () => {
  test("off on a filtered subset of an unrestricted provider writes the rest", () => {
    const fetched = [m("a"), m("b", "embedding"), m("c")];
    const cur = hook([], fetched);
    cur.setMany([fetched[0], fetched[2]], false);
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(written()).toEqual([m("b", "embedding")]);
  });

  test("on from a partial selection adds every missing row once, with its type", () => {
    const fetched = [m("a"), m("b", "embedding"), m("c")];
    const cur = hook([m("a")], fetched);
    cur.setMany(fetched, true);
    expect(written()).toEqual([m("a"), m("b", "embedding"), m("c")]);
  });

  test("a held type correction travels into the added row", () => {
    const fetched = [m("a"), m("b")];
    const { result } = renderHook(() => useModelCuration(provider([m("a")]), fetched));
    // A type picked on a row not offered yet is held, not written.
    act(() => result.current.setModality(fetched[1], "image"));
    expect(mutate).not.toHaveBeenCalled();
    result.current.setMany([fetched[1]], true);
    expect(written()).toEqual([m("a"), m("b", "image")]);
  });

  test("off that would leave nothing on is refused", () => {
    const fetched = [m("a"), m("b")];
    const cur = hook([m("a"), m("b")], fetched);
    expect(cur.wouldEmpty(fetched)).toBe(true);
    expect(cur.canSetMany(fetched, false)).toBe(false);
    cur.setMany(fetched, false);
    expect(mutate).not.toHaveBeenCalled();
    // Same when unrestricted: every row is on, switching them all off is empty.
    const open = hook([], fetched);
    open.setMany(fetched, false);
    expect(mutate).not.toHaveBeenCalled();
  });

  test("nothing to change disables both directions", () => {
    const fetched = [m("a"), m("b")];
    const cur = hook([m("a")], fetched);
    expect(cur.canSetMany([fetched[0]], true)).toBe(false);
    expect(cur.canSetMany([fetched[1]], false)).toBe(false);
    expect(cur.canSetMany([fetched[1]], true)).toBe(true);
    expect(cur.canSetMany([], true)).toBe(false);
  });

  test("prices on rows that stay are preserved", () => {
    const price = { input: 1, output: 2 } as unknown as NonNullable<ProviderModel["price"]>;
    const kept = { ...m("a"), price };
    const fetched = [m("a"), m("b")];
    const cur = hook([kept, m("b")], fetched);
    cur.setMany([fetched[1]], false);
    expect(written()).toEqual([kept]);
    mutate.mockClear();
    const back = hook([kept], fetched);
    back.setMany([fetched[1]], true);
    expect(written()).toEqual([kept, m("b")]);
  });
});
