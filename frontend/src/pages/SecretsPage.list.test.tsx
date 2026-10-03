// src/pages/SecretsPage.list.test.tsx — the Secrets list at scale: readable names, filters, sort, the by-owner view, batching, and bulk selection.
//
// Only the network boundary (`secretsApi`) and the desktop shell's seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type { SecretRef } from "@/lib/api/secret";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SecretsPage } from "./SecretsPage";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(),
    remove: vi.fn(),
    pendingApprovals: vi.fn(),
    refusedApprovals: vi.fn(),
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
    unreferenced: false,
    uri: null,
    ...over,
  };
}

const JIRA = ref({
  ref: "mcp_server/26dddfa9ff00/JIRA_PERSONAL_TOKEN",
  cited_by: [{ kind: "mcp_server", name: "jira", uid: "u-jira" }],
});
const SEATALK = ref({
  ref: "channel/4c838e8fa72e/app-secret",
  cited_by: [{ kind: "channel", name: "seatalk", uid: "u-st" }],
});
const GROQ = ref({
  ref: "provider/b7b7526c/key",
  cited_by: [{ kind: "provider", name: "groq", uid: "u-groq" }],
  readable_by_local_processes: true,
});
const OLD_A = ref({ ref: "secret/old-a", uri: "coffer://secret/old-a", unreferenced: true });
const OLD_B = ref({ ref: "secret/old-b", uri: "coffer://secret/old-b", unreferenced: true });

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderPage(url = "/secrets") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[url]}>
            <Where />
            <Routes>
              <Route path="/secrets" element={<SecretsPage />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const names = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map(
      (r) =>
        within(r).queryByText(/^[A-Za-z0-9_.-]+$/, { selector: "span.font-mono" })?.textContent,
    );
const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  localStorage.clear();
  api.list.mockResolvedValue({ refs: [JIRA, SEATALK, GROQ, OLD_A, OLD_B] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  api.refusedApprovals.mockResolvedValue({ approvals: [] });
  api.remove.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("SecretsPage list", () => {
  acceptance("web-ui", "the secrets page lists each secret with what uses it", async () => {
    renderPage();
    const row = (await screen.findByText("JIRA_PERSONAL_TOKEN")).closest("tr")!;
    expect(within(row).getByText("MCP server · jira")).toBeInTheDocument();
    expect(screen.queryByText(JIRA.ref)).not.toBeInTheDocument();
    const channel = screen.getByText("app-secret").closest("tr")!;
    expect(within(channel).getByText("Channel · seatalk")).toBeInTheDocument();
    // The mark for a value local processes can read stays.
    const groq = screen.getByText("key").closest("tr")!;
    expect(within(groq).getByLabelText("Readable by local processes")).toBeInTheDocument();
    const standalone = screen.getByText("old-a").closest("tr")!;
    expect(within(standalone).getByText("Standalone secret")).toBeInTheDocument();
    // The full reference stays one hover away, and copyable.
    fireEvent.click(within(row).getByRole("button", { name: `Actions for ${JIRA.ref}` }));
    expect(
      screen.getByRole("menuitem", { name: `Copy reference (${JIRA.ref})` }),
    ).toBeInTheDocument();
  });

  test("the status filter has counts and narrows the list; the owner type narrows it too", async () => {
    renderPage();
    await screen.findByText("key");
    expect(screen.getByRole("button", { name: "All 5" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "In use 3" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not used 2" }));
    expect(names()).toEqual(["old-a", "old-b"]);
    expect(where()).toBe("/secrets?status=unused");
    fireEvent.click(screen.getByRole("button", { name: "All 5" }));
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Used by type" }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "Channel" }));
    expect(names()).toEqual(["app-secret"]);
    expect(where()).toBe("/secrets?kind=channel");
  });

  test("a waiting approval and a refusal each have their status", async () => {
    api.pendingApprovals.mockResolvedValue({
      approvals: [
        {
          id: "a1",
          op: "replace_value",
          status: "pending",
          description: "",
          created_at: "2026-09-30T08:00:00Z",
          requested_by: "ui",
          ref: GROQ.ref,
          destination_kind: null,
          destination_label: null,
          destination_uid: null,
          slot: null,
          target: null,
          target_fingerprint: null,
          decided_at: null,
          decided_by: null,
        },
      ],
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Waiting for approval 1" }));
    expect(names()).toEqual(["key"]);
    // Waiting for approval leads the default order too.
    fireEvent.click(screen.getByRole("button", { name: "All 5" }));
    expect(names()[0]).toBe("key");
    expect(screen.getByRole("button", { name: "Refused 0" })).toBeInTheDocument();
  });

  test("filters, sort and view come from the URL", async () => {
    renderPage("/secrets?status=inUse&q=o&sort=name&dir=desc");
    await screen.findByText("key");
    expect((screen.getByRole("textbox", { name: "Find a secret" }) as HTMLInputElement).value).toBe(
      "o",
    );
    // "o" matches app-secret? no — only names or owners containing it: groq's "key" via owner, jira's.
    expect(names()).toEqual(["key", "JIRA_PERSONAL_TOKEN"]);
    expect(screen.getByRole("button", { name: "Sort by Name" })).toHaveAttribute(
      "data-sort",
      "desc",
    );
  });

  test("a column header sorts, then reverses", async () => {
    renderPage();
    await screen.findByText("key");
    expect(names()).toEqual(["app-secret", "JIRA_PERSONAL_TOKEN", "key", "old-a", "old-b"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Name" }));
    fireEvent.click(screen.getByRole("button", { name: "Sort by Name" }));
    expect(names()).toEqual(["old-b", "old-a", "key", "JIRA_PERSONAL_TOKEN", "app-secret"]);
    expect(where()).toBe("/secrets?sort=name&dir=desc");
  });

  test("the by-owner view groups, collapses, and is remembered", async () => {
    renderPage();
    await screen.findByText("key");
    fireEvent.click(screen.getByRole("button", { name: "By owner" }));
    expect(where()).toBe("/secrets?view=owner");
    const jira = screen.getByRole("region", { name: "jira" });
    expect(within(jira).getByText("JIRA_PERSONAL_TOKEN")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Not used by anything" })).toHaveTextContent("old-a");
    fireEvent.click(within(jira).getByRole("button", { expanded: true }));
    expect(screen.queryByText("JIRA_PERSONAL_TOKEN")).not.toBeInTheDocument();
    expect(localStorage.getItem("coffer.secrets.view")).toBe("owner");
  });

  test("a remembered by-owner view opens without the URL naming it", async () => {
    localStorage.setItem("coffer.secrets.view", "owner");
    renderPage();
    expect(await screen.findByRole("region", { name: "groq" })).toBeInTheDocument();
  });

  acceptance("web-ui", "the secrets page lists each secret with what uses it", async () => {
    const many = Array.from({ length: 1000 }, (_, i) =>
      ref({
        ref: `secret/key-${String(i).padStart(4, "0")}`,
        uri: `coffer://secret/key-${String(i).padStart(4, "0")}`,
        unreferenced: true,
      }),
    );
    api.list.mockResolvedValue({ refs: many });
    renderPage();
    await screen.findByText("key-0000");
    expect(screen.getAllByRole("row")).toHaveLength(51);
    expect(screen.getByText("Showing 50 of 1000")).toBeInTheDocument();
    expect(screen.queryByText("key-0999")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load 50 more" }));
    expect(screen.getAllByRole("row")).toHaveLength(101);
    fireEvent.change(screen.getByRole("textbox", { name: "Find a secret" }), {
      target: { value: "key-0999" },
    });
    expect(await screen.findByText("key-0999")).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 1")).toBeInTheDocument();
  });

  test("ticking a secret swaps the filters for the selection bar, which selects all matching", async () => {
    renderPage();
    await screen.findByText("key");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-a" }));
    const bar = screen.getByRole("region", { name: "Selected secrets" });
    expect(bar).toHaveTextContent("1 selected");
    expect(screen.queryByRole("textbox", { name: "Find a secret" })).not.toBeInTheDocument();
    fireEvent.click(within(bar).getByRole("checkbox", { name: "Select all secrets" }));
    expect(bar).toHaveTextContent("5 selected");
    fireEvent.click(within(bar).getByRole("button", { name: "Clear" }));
    expect(screen.getByRole("textbox", { name: "Find a secret" })).toBeInTheDocument();
  });

  acceptance("web-ui", "a secret in use cannot be deleted from the secrets page", async () => {
    renderPage();
    await screen.findByText("key");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-a" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select key" }));
    const bar = screen.getByRole("region", { name: "Selected secrets" });
    const del = within(bar).getByRole("button", { name: "Delete" });
    expect(del).toBeDisabled();
    expect(del).toHaveAttribute("title", "1 in use or waiting for approval");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select key" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-b" }));
    fireEvent.click(within(bar).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete 2 secrets?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 secrets" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledTimes(2));
    expect(api.remove).toHaveBeenCalledWith("secret/old-a");
    expect(api.remove).toHaveBeenCalledWith("secret/old-b");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("Delete unused… confirms with the count and names, then deletes only unused secrets", async () => {
    renderPage();
    await screen.findByText("key");
    fireEvent.click(screen.getByRole("button", { name: "Delete unused…" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete 2 secrets?" });
    expect(dialog).toHaveTextContent("old-a and old-b");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 secrets" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledTimes(2));
    expect(api.remove).not.toHaveBeenCalledWith(JIRA.ref);
  });

  test("no Delete unused… when everything is in use", async () => {
    api.list.mockResolvedValue({ refs: [JIRA] });
    renderPage();
    await screen.findByText("JIRA_PERSONAL_TOKEN");
    expect(screen.queryByRole("button", { name: "Delete unused…" })).not.toBeInTheDocument();
  });
});
