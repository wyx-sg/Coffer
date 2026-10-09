// src/components/providers/labelNewKey.test.ts — the secrets list is read again after the new key's label is written.
import { afterEach, describe, expect, test, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { secretsListKey } from "@/lib/api/queryKeys";
import { labelNewKey } from "./labelNewKey";

vi.mock("@/lib/api/secret", () => ({ secretsApi: { setNotes: vi.fn() } }));
const { secretsApi } = await import("@/lib/api/secret");
const setNotes = vi.mocked(secretsApi.setNotes);

const NEW = {
  kind: "new",
  name: "openai-key",
  value: "x",
  label: " qa provider API key ",
} as const;

function warmClient() {
  const qc = new QueryClient();
  // A list read before the label existed: the key shows as "Unnamed secret".
  qc.setQueryData(secretsListKey, { items: [] });
  return qc;
}

afterEach(() => vi.clearAllMocks());

describe("labelNewKey", () => {
  test("writes the label, then marks the cached secrets stale", async () => {
    const qc = warmClient();
    let staleWhenWritten: boolean | undefined;
    setNotes.mockImplementation(async () => {
      staleWhenWritten = qc.getQueryState(secretsListKey)?.isInvalidated;
      return {} as never;
    });
    await labelNewKey(qc, NEW, "secret/abc");
    expect(setNotes).toHaveBeenCalledWith("secret/abc", { label: "qa provider API key" });
    // Invalidated after the write, not only before it.
    expect(staleWhenWritten).toBe(false);
    expect(qc.getQueryState(secretsListKey)?.isInvalidated).toBe(true);
  });

  test("a failed label write still refreshes the list (the key itself is new)", async () => {
    const qc = warmClient();
    setNotes.mockRejectedValue(new Error("down"));
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    await labelNewKey(qc, NEW, "secret/abc");
    expect(qc.getQueryState(secretsListKey)?.isInvalidated).toBe(true);
  });

  test("a stored key chosen from the list writes no label but refreshes", async () => {
    const qc = warmClient();
    await labelNewKey(qc, { kind: "stored", name: "old" }, "secret/old");
    expect(setNotes).not.toHaveBeenCalled();
    expect(qc.getQueryState(secretsListKey)?.isInvalidated).toBe(true);
  });
});
