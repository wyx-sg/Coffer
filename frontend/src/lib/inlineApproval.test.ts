// src/lib/inlineApproval.test.ts — a save in the desktop app approves what it left waiting, on the spot.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/secret", () => ({ secretsApi: { pendingApprovals: vi.fn() } }));
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: vi.fn(() => true),
  approvePending: vi.fn(async () => ({})),
  approvePendingBatch: vi.fn(async () => ({ results: [] })),
}));

const { secretsApi } = await import("@/lib/api/secret");
const tauri = await import("@/lib/tauri");
const {
  approvalsHeld,
  approveWhatTheSaveAwaits,
  DECLINED_APPROVALS_EVENT,
  inlineApprovalMutationCache,
  withInlineApproval,
} = await import("./inlineApproval");

const pending = vi.mocked(secretsApi.pendingApprovals);
const now = () => new Date().toISOString();
const approval = (id: string, uid: string, created_at = now(), op = "bind") => ({
  id,
  op,
  status: "pending",
  destination_uid: uid,
  created_at,
  requested_by: "ui",
});

beforeEach(() => {
  vi.mocked(tauri.presenceAvailable).mockReturnValue(true);
});
afterEach(() => vi.clearAllMocks());

describe("approveWhatTheSaveAwaits", () => {
  test("approves only the bindings this save created on this destination", async () => {
    const since = Date.now();
    pending.mockResolvedValue({
      approvals: [
        approval("mine", "uid-1"),
        approval("other-resource", "uid-2"),
        approval("older", "uid-1", new Date(since - 60_000).toISOString()),
        approval("protection", "uid-1", now(), "disable_protection"),
      ],
    } as never);
    expect(await approveWhatTheSaveAwaits("uid-1", since)).toBe("approved");
    expect(tauri.approvePending).toHaveBeenCalledWith("mine");
    expect(tauri.approvePendingBatch).not.toHaveBeenCalled();
  });

  acceptance(
    "desktop-app",
    "a save in the app approves its own binding with one presence check",
    async () => {
      pending.mockResolvedValue({
        approvals: [
          approval("a", "uid-1"),
          approval("b", "uid-1"),
          approval("elsewhere", "uid-2"),
          approval("before", "uid-1", new Date(Date.now() - 60_000).toISOString()),
        ],
      } as never);
      expect(await approveWhatTheSaveAwaits("uid-1", Date.now())).toBe("approved");
      expect(tauri.approvePendingBatch).toHaveBeenCalledWith(["a", "b"]);
    },
  );

  test("nothing waiting asks for nothing", async () => {
    pending.mockResolvedValue({ approvals: [] } as never);
    expect(await approveWhatTheSaveAwaits("uid-1", Date.now())).toBe("none");
    expect(tauri.approvePending).not.toHaveBeenCalled();
  });

  test("a cancelled prompt leaves it waiting and keeps the sheet shut over it", async () => {
    pending.mockResolvedValue({ approvals: [approval("mine", "uid-1")] } as never);
    vi.mocked(tauri.approvePending).mockRejectedValueOnce(new Error("cancelled"));
    const declined = vi.fn();
    window.addEventListener(DECLINED_APPROVALS_EVENT, declined);
    expect(await approveWhatTheSaveAwaits("uid-1", Date.now())).toBe("declined");
    window.removeEventListener(DECLINED_APPROVALS_EVENT, declined);
    expect((declined.mock.calls[0][0] as CustomEvent).detail).toEqual(["mine"]);
  });
});

describe("withInlineApproval", () => {
  test("holds the sheet while it saves and approves", async () => {
    pending.mockResolvedValue({ approvals: [approval("mine", "uid-1")] } as never);
    let heldDuringSave = false;
    const result = await withInlineApproval(
      async () => {
        heldDuringSave = approvalsHeld();
        return { uid: "uid-1" };
      },
      (r) => r.uid,
    );
    expect(result).toEqual({ uid: "uid-1" });
    expect(heldDuringSave).toBe(true);
    expect(approvalsHeld()).toBe(false);
    expect(tauri.approvePending).toHaveBeenCalledWith("mine");
  });

  acceptance("desktop-app", "a save in a browser leaves its approval waiting", async () => {
    vi.mocked(tauri.presenceAvailable).mockReturnValue(false);
    await withInlineApproval(
      async () => "ok",
      () => "uid-1",
    );
    expect(pending).not.toHaveBeenCalled();
    expect(tauri.approvePending).not.toHaveBeenCalled();
  });
});

describe("a batch of saves", () => {
  test("approves what every new resource waits on under one presence check", async () => {
    pending.mockResolvedValue({
      approvals: [approval("a", "uid-1"), approval("b", "uid-2"), approval("c", "uid-3")],
    } as never);
    await withInlineApproval(
      async () => ["uid-1", "uid-2"],
      (uids) => uids,
    );
    expect(tauri.approvePendingBatch).toHaveBeenCalledWith(["a", "b"]);
    expect(tauri.approvePending).not.toHaveBeenCalled();
  });
});

describe("the mutation cache", () => {
  test("a mutation that names its destination approves before it resolves", async () => {
    pending.mockResolvedValue({ approvals: [approval("mine", "uid-9")] } as never);
    const qc = new QueryClient({ mutationCache: inlineApprovalMutationCache() });
    const mutation = qc.getMutationCache().build(qc, {
      mutationFn: async (uid: string) => ({ uid }),
      meta: { secretDestination: (data: unknown) => (data as { uid: string }).uid },
    });
    await mutation.execute("uid-9");
    expect(tauri.approvePending).toHaveBeenCalledWith("mine");
    expect(approvalsHeld()).toBe(false);
  });

  test("a mutation that does not opt in never asks", async () => {
    const qc = new QueryClient({ mutationCache: inlineApprovalMutationCache() });
    const mutation = qc.getMutationCache().build(qc, { mutationFn: async () => "x" });
    await mutation.execute(undefined);
    expect(pending).not.toHaveBeenCalled();
  });

  test("a failed save releases the hold", async () => {
    const qc = new QueryClient({ mutationCache: inlineApprovalMutationCache() });
    const mutation = qc.getMutationCache().build(qc, {
      mutationFn: async () => {
        throw new Error("boom");
      },
      meta: { secretDestination: () => "uid-1" },
    });
    await expect(mutation.execute(undefined)).rejects.toThrow("boom");
    expect(approvalsHeld()).toBe(false);
    expect(pending).not.toHaveBeenCalled();
  });
});
