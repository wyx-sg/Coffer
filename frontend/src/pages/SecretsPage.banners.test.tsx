// src/pages/SecretsPage.banners.test.tsx — the two banners above the Secrets list, their × (Ignore, shared with Overview), and the add-values dialog.
//
// Only the network boundary (`secretsApi`, `attentionApi`) and the desktop shell's seam are mocked.
import { acceptance } from "@/test/acceptance";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { Approval, SecretRef } from "@/lib/api/secret";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { OPEN_APPROVALS_EVENT } from "@/lib/hooks/useApprovals";
import { SecretsPage } from "./SecretsPage";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(),
    set: vi.fn(),
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
  },
}));
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => false,
  revealSecret: vi.fn(),
  approvePending: vi.fn(),
  onApprovalsEvent: () => () => {},
}));
vi.mock("@/lib/hooks/useFeatures", () => ({ useKindPageOpen: () => () => true }));

function item(reason_code: string, key: string) {
  return {
    kind: "secret",
    uid: "fp",
    key,
    title: "Secrets",
    reason: "…",
    reason_code,
    severity: "error",
    since: null,
    action: { verb: "open", method: "GET", path: "/api/v1/secrets" },
    handoff: { prompt: "" },
  };
}
let attention: { items: unknown[]; ignored: unknown[] } = { items: [], ignored: [] };
const ignoreAttention = vi.fn().mockResolvedValue(undefined);
vi.mock("@/lib/api/attention", () => ({
  attentionApi: {
    read: () => Promise.resolve({ ...attention, counts_by_kind: {}, errors: [] }),
    ignore: (key: string) => ignoreAttention(key),
    unignore: vi.fn(),
  },
}));

const { secretsApi } = await import("@/lib/api/secret");
const api = vi.mocked(secretsApi);

function ref(over: Partial<SecretRef> & { ref: string }): SecretRef {
  return {
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    present: true,
    locked: false,
    created_at: "2026-08-12T09:00:00Z",
    last_used_at: null,
    readable_by_local_processes: false,
    local_access: null,
    unreferenced: false,
    uri: null,
    label: null,
    description: null,
    created_for: null,
    ...over,
  };
}
const LINEAR = ref({
  ref: "secret/linear-api-key",
  label: "linear-api-key",
  uri: "coffer://secret/linear-api-key",
  present: false,
  cited_by: [{ kind: "mcp_server", name: "linear", uid: "l", slot: null }],
});
const SENTRY = ref({
  ref: "secret/sentry-token",
  label: "sentry-token",
  uri: "coffer://secret/sentry-token",
  locked: true,
  cited_by: [{ kind: "mcp_server", name: "sentry", uid: "s", slot: null }],
});
const GITHUB = ref({
  ref: "secret/github-token",
  label: "github-token",
  uri: "coffer://secret/github-token",
  cited_by: [{ kind: "mcp_server", name: "github", uid: "g", slot: null }],
});

function approval(id: string, over: Partial<Approval> = {}): Approval {
  return {
    id,
    op: "bind",
    status: "pending",
    description: "",
    created_at: "2026-09-30T08:00:00Z",
    requested_by: "ui",
    ref: GITHUB.ref,
    destination_kind: null,
    destination_label: null,
    destination_uid: null,
    slot: null,
    target: null,
    target_fingerprint: null,
    decided_at: null,
    decided_by: null,
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={["/secrets"]}>
            <Routes>
              <Route path="/secrets" element={<SecretsPage />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  attention = { items: [], ignored: [] };
  api.list.mockResolvedValue({ refs: [LINEAR, SENTRY, GITHUB] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  api.set.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("Secrets banners", () => {
  test("missing sits above waiting, each with one action and an ×", async () => {
    api.pendingApprovals.mockResolvedValue({
      approvals: [approval("a1"), approval("a2", { op: "disable_protection", ref: "secret/npm" })],
    });
    renderPage();
    const missing = await screen.findByTestId("secrets-missing-banner");
    const waiting = await screen.findByTestId("pending-approvals-entry");
    expect(
      missing.compareDocumentPosition(waiting) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(missing).toHaveTextContent("2 secrets have no value on this Mac");
    expect(missing).toHaveTextContent("linear and sentry can’t start until they have a value.");
    expect(waiting).toHaveTextContent("2 changes waiting for approval");
    expect(waiting).toHaveTextContent("Changes to github-token and 1 more.");
    expect(waiting).toHaveTextContent("Approving asks for Touch ID or your login password.");
    expect(within(waiting).getByRole("button", { name: "Review" })).toBeInTheDocument();
  });

  test("the waiting banner names its secret, and Review opens the global approvals dialog", async () => {
    api.pendingApprovals.mockResolvedValue({ approvals: [approval("a1")] });
    const opened = vi.fn();
    window.addEventListener(OPEN_APPROVALS_EVENT, opened);
    renderPage();
    const waiting = await screen.findByTestId("pending-approvals-entry");
    expect(waiting).toHaveTextContent("1 change waiting for approval");
    expect(waiting).toHaveTextContent("A new use of github-token.");
    act(() => {
      fireEvent.click(within(waiting).getByRole("button", { name: "Review" }));
    });
    expect(opened).toHaveBeenCalled();
    window.removeEventListener(OPEN_APPROVALS_EVENT, opened);
  });

  acceptance("web-ui", "a page banner's × ignores the item on Overview too", async () => {
    attention = {
      items: [item("secret_missing_here", "secret:fp:secret_missing_here")],
      ignored: [],
    };
    renderPage();
    const missing = await screen.findByTestId("secrets-missing-banner");
    // × only once the daemon's attention list names the item.
    const close = await within(missing).findByRole("button", { name: "Ignore" });
    fireEvent.click(close);
    await waitFor(() =>
      expect(ignoreAttention).toHaveBeenCalledWith("secret:fp:secret_missing_here"),
    );
  });

  test("a banner ignored on Overview is hidden here, and the row's status stays", async () => {
    attention = {
      items: [],
      ignored: [item("secret_missing_here", "secret:fp:secret_missing_here")],
    };
    renderPage();
    const row = (await screen.findByText("linear-api-key")).closest("li")!;
    expect(within(row).getByText("No value on this Mac")).toBeInTheDocument();
    expect(screen.queryByTestId("secrets-missing-banner")).toBeNull();
  });

  test("Add values saves only the filled rows, one PUT each", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Add values" }));
    const dialog = await screen.findByRole("dialog", { name: "Add values on this Mac" });
    expect(dialog).toHaveTextContent("Used by linear");
    const save = within(dialog).getByRole("button", { name: "Save 0 values" });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Value for linear-api-key"), {
      target: { value: "lin_x" },
    });
    expect(within(dialog).getByRole("button", { name: "Save 1 value" })).toBeEnabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save 1 value" }));
    await waitFor(() => expect(api.set).toHaveBeenCalledTimes(1));
    expect(api.set).toHaveBeenCalledWith("secret/linear-api-key", "lin_x");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
