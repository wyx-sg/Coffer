// frontend/src/lib/filePicker.test.ts
//
// In the browser (jsdom — not Tauri) the file pickers delegate to the daemon
// (fsApi.pickFile / saveFile) and translate `available` into `unavailable` so a
// no-native-dialog host can fall back to a typed path. We mock fsApi.

import { afterEach, describe, expect, test, vi } from "vitest";

import { pickOpenFile, pickSaveFile } from "./filePicker";

vi.mock("@/lib/api/fs", () => ({
  fsApi: { pickFile: vi.fn(), saveFile: vi.fn() },
}));
const { fsApi } = await import("@/lib/api/fs");
const pickFileMock = vi.mocked(fsApi.pickFile);
const saveFileMock = vi.mocked(fsApi.saveFile);

afterEach(() => vi.clearAllMocks());

describe("pickOpenFile (web)", () => {
  test("returns the chosen path and unavailable:false", async () => {
    pickFileMock.mockResolvedValue({ available: true, path: "/Users/me/coffer.key" });
    expect(await pickOpenFile("/Users/me")).toEqual({
      path: "/Users/me/coffer.key",
      unavailable: false,
    });
    expect(pickFileMock).toHaveBeenCalledWith("/Users/me");
  });

  test("maps a cancel (available:true, path:null) to a null path, still available", async () => {
    pickFileMock.mockResolvedValue({ available: true, path: null });
    expect(await pickOpenFile()).toEqual({ path: null, unavailable: false });
  });

  test("maps available:false to unavailable:true (fall back to typing)", async () => {
    pickFileMock.mockResolvedValue({ available: false, path: null });
    expect(await pickOpenFile()).toEqual({ path: null, unavailable: true });
  });

  test("treats a daemon error as unavailable", async () => {
    pickFileMock.mockRejectedValue(new Error("network down"));
    expect(await pickOpenFile()).toEqual({ path: null, unavailable: true });
  });
});

describe("pickSaveFile (web)", () => {
  test("passes the suggested name through and returns the destination", async () => {
    saveFileMock.mockResolvedValue({ available: true, path: "/Users/me/out.key" });
    expect(await pickSaveFile("coffer-master.key")).toEqual({
      path: "/Users/me/out.key",
      unavailable: false,
    });
    expect(saveFileMock).toHaveBeenCalledWith("coffer-master.key", undefined);
  });

  test("maps available:false to unavailable:true", async () => {
    saveFileMock.mockResolvedValue({ available: false, path: null });
    expect(await pickSaveFile("x.key")).toEqual({ path: null, unavailable: true });
  });
});
