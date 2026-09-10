// frontend/src/lib/filePicker.test.ts
//
// The folder picker delegates to the daemon (fsApi.pickFolder) and translates
// `available` into `unavailable` so a no-native-dialog host can fall back to a
// typed path. We mock fsApi.

import { afterEach, describe, expect, test, vi } from "vitest";

import { pickDirectory } from "./filePicker";

vi.mock("@/lib/api/fs", () => ({
  fsApi: { pickFolder: vi.fn() },
}));
const { fsApi } = await import("@/lib/api/fs");
const pickFolderMock = vi.mocked(fsApi.pickFolder);

afterEach(() => vi.clearAllMocks());

describe("pickDirectory (web)", () => {
  test("returns the chosen path and unavailable:false", async () => {
    pickFolderMock.mockResolvedValue({ available: true, path: "/Users/me/bundle" });
    expect(await pickDirectory("/Users/me")).toEqual({
      path: "/Users/me/bundle",
      unavailable: false,
    });
    expect(pickFolderMock).toHaveBeenCalledWith("/Users/me");
  });

  test("maps a cancel (available:true, path:null) to a null path, still available", async () => {
    pickFolderMock.mockResolvedValue({ available: true, path: null });
    expect(await pickDirectory()).toEqual({ path: null, unavailable: false });
  });

  test("maps available:false to unavailable:true (fall back to typing)", async () => {
    pickFolderMock.mockResolvedValue({ available: false, path: null });
    expect(await pickDirectory()).toEqual({ path: null, unavailable: true });
  });

  test("treats a daemon error as unavailable", async () => {
    pickFolderMock.mockRejectedValue(new Error("network down"));
    expect(await pickDirectory()).toEqual({ path: null, unavailable: true });
  });
});
