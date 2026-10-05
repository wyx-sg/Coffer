// src/components/secret/SecretOverview.test.tsx — the Access row of a standalone secret:
// off offers "Allow coffer run…", pending says it waits, on offers Revoke; each calls the API.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { acceptance } from "@/test/acceptance";
import type { SecretRef } from "@/lib/api/secret";
import { secretsApi } from "@/lib/api/secret";
import { inlineApprovalMutationCache } from "@/lib/inlineApproval";
import { approvePending } from "@/lib/tauri";
import { SecretOverview } from "./SecretOverview";

let inShell = false;
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => inShell,
  approvePending: vi.fn(async () => ({})),
  approvePendingBatch: vi.fn(async () => ({ results: [] })),
}));

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    requestLocalAccess: vi.fn(async () => ({ local_access: "pending", approval_id: "a1" })),
    revokeLocalAccess: vi.fn(async () => ({ local_access: "off", approval_id: null })),
    list: vi.fn(async () => ({ refs: [] })),
    pendingApprovals: vi.fn(async () => ({ approvals: [] })),
  },
}));

const NAME = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

function row(over: Partial<SecretRef>): SecretRef {
  return {
    ref: `secret/${NAME}`,
    label: "Key",
    uri: `coffer://secret/${NAME}`,
    present: true,
    locked: false,
    created_at: null,
    last_used_at: null,
    cited_by: [],
    mentioned_by_skills: [],
    bindings: [],
    unreferenced: true,
    readable_by_local_processes: false,
    local_access: "off",
    description: null,
    created_for: null,
    ...over,
  } as SecretRef;
}

function renderRow(r: SecretRef) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
    mutationCache: inlineApprovalMutationCache(),
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <SecretOverview row={r} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("SecretOverview Access row", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    inShell = false;
  });

  test("off: says only Coffer uses it and Allow requests the grant", async () => {
    renderRow(row({ local_access: "off" }));
    expect(screen.getByTestId("local-access-state").textContent).toMatch(/Only Coffer uses it/);
    fireEvent.click(screen.getByRole("button", { name: "Allow coffer run…" }));
    await waitFor(() => expect(secretsApi.requestLocalAccess).toHaveBeenCalledWith(NAME));
    // In a browser there is no presence check: the request waits.
    expect(approvePending).not.toHaveBeenCalled();
  });

  acceptance(
    "secret",
    "allowing coffer run in the desktop app asks for Touch ID at once",
    async () => {
      inShell = true;
      vi.mocked(secretsApi.pendingApprovals).mockResolvedValueOnce({
        approvals: [
          {
            id: "a1",
            op: "bind",
            destination_uid: "coffer-run",
            created_at: new Date().toISOString(),
          },
        ],
      } as never);
      renderRow(row({ local_access: "off" }));
      fireEvent.click(screen.getByRole("button", { name: "Allow coffer run…" }));
      await waitFor(() => expect(approvePending).toHaveBeenCalledWith("a1"));
    },
  );

  test("pending: waits for approval and offers no button", () => {
    renderRow(
      row({
        local_access: "pending",
        bindings: [
          {
            destination_kind: "local_process",
            destination_uid: "coffer-run",
            slot: "env",
            status: "pending",
          },
        ],
      } as Partial<SecretRef>),
    );
    expect(screen.getByText("Waiting for your approval in the Coffer app")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Allow coffer run…" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Revoke" })).toBeNull();
    // The Access row carries it: the used-by list does not repeat it.
    expect(screen.getAllByText("Waiting for your approval in the Coffer app")).toHaveLength(1);
  });

  test("on: says it can be handed to programs and Revoke withdraws it", async () => {
    renderRow(row({ local_access: "on", readable_by_local_processes: true }));
    expect(screen.getByTestId("local-access-state").textContent).toMatch(/hand it to programs/);
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(secretsApi.revokeLocalAccess).toHaveBeenCalledWith(NAME));
  });

  test("a resource's secret has no Allow or Revoke", () => {
    renderRow(row({ ref: "mcp_server/u/TOKEN", local_access: null, uri: null }));
    expect(screen.queryByRole("button", { name: "Allow coffer run…" })).toBeNull();
  });
});
