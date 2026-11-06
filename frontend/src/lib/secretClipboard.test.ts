// src/lib/secretClipboard.test.ts — a revealed value is copied through the shell, which marks it
// concealed and clears it after 90 seconds; off a Mac the page writes the clipboard itself.
import { afterEach, describe, expect, test, vi } from "vitest";

import en from "@/i18n/locales/en.json";
import { acceptance } from "@/test/acceptance";
import { copySecretValue } from "./secretClipboard";

const invokeMock = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

const TAURI_KEY = "__TAURI_INTERNALS__";
const enterTauri = () => {
  (window as unknown as Record<string, unknown>)[TAURI_KEY] = {};
};
const leaveTauri = () => {
  delete (window as unknown as Record<string, unknown>)[TAURI_KEY];
};

describe("copySecretValue", () => {
  afterEach(() => {
    leaveTauri();
    invokeMock.mockReset();
  });

  acceptance("secret", "copying a revealed value goes through the shell", async () => {
    enterTauri();
    invokeMock.mockResolvedValue(undefined);
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    await copySecretValue("s3cret-value");

    expect(invokeMock).toHaveBeenCalledWith("copy_secret", { value: "s3cret-value" });
    expect(writeText).not.toHaveBeenCalled();
    expect(en.secrets.reveal.copied).toContain("90 seconds");
  });

  test("off a Mac the shell refuses and the page writes the clipboard itself", async () => {
    enterTauri();
    invokeMock.mockRejectedValue("macOS only");
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    await copySecretValue("v");

    expect(writeText).toHaveBeenCalledWith("v");
  });
});
