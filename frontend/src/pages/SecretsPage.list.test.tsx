// src/pages/SecretsPage.list.test.tsx — the Secrets list pane at scale: readable names, status and search, batching, and bulk selection.
//
// Only the network boundary (`secretsApi`) and the desktop shell's seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type { SecretRef } from "@/lib/api/secret";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SecretsPage } from "./SecretsPage";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(),
    remove: vi.fn(),
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
  },
}));
vi.mock("@/lib/api/attention", () => ({
  attentionApi: {
    read: () => Promise.resolve({ items: [], ignored: [], counts_by_kind: {}, errors: [] }),
    ignore: vi.fn(),
    unignore: vi.fn(),
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
    local_access: null,
    unreferenced: false,
    uri: null,
    label: null,
    description: null,
    created_for: null,
    ...over,
  };
}

const JIRA = ref({
  ref: "mcp_server/26dddfa9ff00/JIRA_PERSONAL_TOKEN",
  label: "jira · JIRA_PERSONAL_TOKEN",
  cited_by: [{ kind: "mcp_server", name: "jira", uid: "u-jira", slot: null }],
});
const SEATALK = ref({
  ref: "channel/4c838e8fa72e/app-secret",
  label: "seatalk · app-secret",
  cited_by: [{ kind: "channel", name: "seatalk", uid: "u-st", slot: null }],
});
const GROQ = ref({
  ref: "provider/b7b7526c/key",
  label: "groq · key",
  cited_by: [{ kind: "provider", name: "groq", uid: "u-groq", slot: null }],
  readable_by_local_processes: true,
  local_access: null,
});
const OLD_A = ref({
  ref: "secret/old-a",
  label: "old-a",
  uri: "coffer://secret/old-a",
  unreferenced: true,
  last_used_at: "2026-09-01T10:00:00Z",
  created_at: "2026-03-02T10:00:00Z",
});
const OLD_B = ref({
  ref: "secret/old-b",
  label: "old-b",
  uri: "coffer://secret/old-b",
  unreferenced: true,
  last_used_at: "2026-09-20T10:00:00Z",
  created_at: "2026-06-02T10:00:00Z",
});

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
              <Route path="/secrets/:id" element={<SecretsPage />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const names = () =>
  within(screen.getByRole("group", { name: "Secrets" }))
    .getAllByRole("link")
    .map((a) => a.querySelector("span.font-label")?.textContent);
const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  localStorage.clear();
  api.list.mockResolvedValue({ refs: [JIRA, SEATALK, GROQ, OLD_A, OLD_B] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  api.remove.mockResolvedValue(undefined);
});
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("SecretsPage list", () => {
  test("a secret is listed by a readable name, never a hex id, and opens on its own page", async () => {
    const hex = ref({
      ref: "secret/0123456789abcdef0123456789abcdef",
      cited_by: [{ kind: "mcp_server", name: "server", uid: "u-s", slot: null }],
      bindings: [
        {
          approval_id: null,
          destination_kind: "mcp_server",
          destination_uid: "u-s",
          slot: "API_KEY",
          status: "approved" as const,
        },
      ],
    });
    api.list.mockResolvedValue({ refs: [JIRA, hex, OLD_A] });
    renderPage();
    // An unlabelled secret reads "citer · slot"; a labelled one reads its label.
    expect(await screen.findByText("jira · JIRA_PERSONAL_TOKEN")).toBeInTheDocument();
    expect(screen.getByText("server · API_KEY")).toBeInTheDocument();
    expect(screen.queryByText(/0123456789abcdef/)).not.toBeInTheDocument();
    // What uses a secret is a count on the row, with no popover.
    const row = screen.getByText("jira · JIRA_PERSONAL_TOKEN").closest("li")!;
    expect(within(row).getByText("used by 1")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /is used by/ })).toBeNull();
    fireEvent.click(within(row).getByRole("link"));
    expect(where()).toBe(`/secrets/${encodeURIComponent(JIRA.ref)}`);
  });

  test("the Status filter has no counts, narrows the list, and the list is grouped", async () => {
    renderPage();
    await screen.findByText("groq · key");
    // In use, then Not used, each under its heading.
    expect(screen.getByRole("region", { name: "In use" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Not used" })).toBeInTheDocument();
    const status = screen.getByRole("combobox", { name: "Status" });
    expect(status).toHaveTextContent("All");
    // Radix Select opens from the keyboard in jsdom (no PointerEvent).
    fireEvent.keyDown(status, { key: "ArrowDown" });
    expect(screen.queryByRole("option", { name: /Waiting|Refused/ })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("option", { name: "Not used" }));
    await waitFor(() => expect(names()).toEqual(["old-a", "old-b"]));
    expect(where()).toBe("/secrets?status=unused");
    // One filter only: no type dropdown, no by-owner view.
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "By owner" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete unused/ })).not.toBeInTheDocument();
  });

  test("no match offers Clear filters, which resets the search and the status", async () => {
    renderPage("/secrets?status=unused&q=nothing-here");
    expect(await screen.findByText("No secret matches “nothing-here”")).toBeInTheDocument();
    const clears = screen.getAllByRole("button", { name: "Clear filter" });
    fireEvent.click(clears[clears.length - 1]);
    expect(where()).toBe("/secrets");
    expect(await screen.findByText("groq · key")).toBeInTheDocument();
  });

  test("a destination waiting for approval puts its row first, with its status word", async () => {
    api.list.mockResolvedValue({
      refs: [
        JIRA,
        SEATALK,
        {
          ...GROQ,
          bindings: [
            {
              approval_id: "a1",
              destination_kind: "provider",
              destination_uid: "b7b7",
              slot: "key",
              status: "pending",
            },
          ],
        },
        OLD_A,
        OLD_B,
      ],
    });
    renderPage();
    const row = (await screen.findByText("groq · key")).closest("li")!;
    expect(await within(row).findByText("Waiting for approval")).toBeInTheDocument();
    expect(names()[0]).toBe("groq · key");
    expect(screen.queryByText("Refused")).not.toBeInTheDocument();
  });

  test("search and status come from the URL", async () => {
    renderPage("/secrets?status=inUse&q=o");
    await screen.findByText("groq · key");
    expect((screen.getByRole("textbox", { name: "Find a secret" }) as HTMLInputElement).value).toBe(
      "o",
    );
    // "o" matches a secret's display name or reference; unused ones are out.
    expect(names()).toEqual(["groq · key", "jira · JIRA_PERSONAL_TOKEN"]);
  });

  test("a thousand secrets render 100 at a time as the end scrolls into view, while search covers all of them", async () => {
    const observed: { callback: IntersectionObserverCallback }[] = [];
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: IntersectionObserverCallback) {
          observed.push({ callback });
        }
        observe() {}
        disconnect() {}
      },
    );
    const many = Array.from({ length: 1000 }, (_, i) =>
      ref({
        ref: `secret/key-${String(i).padStart(4, "0")}`,
        uri: `coffer://secret/key-${String(i).padStart(4, "0")}`,
        label: `key-${String(i).padStart(4, "0")}`,
        unreferenced: true,
      }),
    );
    api.list.mockResolvedValue({ refs: many });
    renderPage();
    await screen.findByText("key-0000");
    expect(names()).toHaveLength(100);
    expect(screen.queryByRole("button", { name: /load/i })).toBeNull();
    expect(screen.queryByText("key-0999")).not.toBeInTheDocument();
    act(() =>
      observed
        .at(-1)
        ?.callback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          {} as IntersectionObserver,
        ),
    );
    expect(names()).toHaveLength(200);
    fireEvent.change(screen.getByRole("textbox", { name: "Find a secret" }), {
      target: { value: "key-0999" },
    });
    expect(await screen.findByText("key-0999")).toBeInTheDocument();
    expect(screen.queryByText(/^Showing/)).toBeNull();
  });

  test("the header box selects every secret the filters show, and the bar reads N of M", async () => {
    renderPage();
    await screen.findByText("groq · key");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-a" }));
    const bar = screen.getByRole("region", { name: "Selected secrets" });
    expect(bar).toHaveTextContent("1 of 5 selected");
    expect(screen.queryByRole("textbox", { name: "Find a secret" })).not.toBeInTheDocument();
    expect(within(bar).queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all" }));
    expect(bar).toHaveTextContent("5 of 5 selected");
    // Esc clears the selection and brings the filters back.
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("textbox", { name: "Find a secret" })).toBeInTheDocument();
  });

  test("a bulk delete skips and names what is in use, and deletes only the rest", async () => {
    renderPage();
    await screen.findByText("groq · key");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-a" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select groq · key" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-b" }));
    const bar = screen.getByRole("region", { name: "Selected secrets" });
    // A secret in use does not turn Delete off: the confirmation names it and skips it.
    const del = within(bar).getByRole("button", { name: "Delete…" });
    expect(del).toBeEnabled();
    fireEvent.click(del);
    const dialog = await screen.findByRole("dialog", { name: "Delete 3 secrets?" });
    expect(dialog).toHaveTextContent("old-a and old-b");
    expect(dialog).toHaveTextContent("groq · key is in use and will be skipped.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 secrets" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledTimes(2));
    expect(api.remove).toHaveBeenCalledWith("secret/old-a");
    expect(api.remove).toHaveBeenCalledWith("secret/old-b");
    expect(api.remove).not.toHaveBeenCalledWith(GROQ.ref);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
