// src/pages/SecretsPage.list.test.tsx — the Secrets list at scale: readable names, status and search, time-column sort, batching, and bulk selection.
//
// Only the network boundary (`secretsApi`) and the desktop shell's seam are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const OLD_A = ref({
  ref: "secret/old-a",
  uri: "coffer://secret/old-a",
  unreferenced: true,
  last_used_at: "2026-09-01T10:00:00Z",
  created_at: "2026-03-02T10:00:00Z",
});
const OLD_B = ref({
  ref: "secret/old-b",
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
  api.remove.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("SecretsPage list", () => {
  test("a secret is listed by its own short name, with its users in the Used by column", async () => {
    renderPage();
    const row = (await screen.findByText("JIRA_PERSONAL_TOKEN")).closest("tr")!;
    // No owner line under the name: what uses a secret is the Used by column.
    expect(within(row).queryByText("MCP server · jira")).not.toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /is used by 1 thing/ })).toHaveTextContent(
      "jira",
    );
    expect(screen.queryByText(JIRA.ref)).not.toBeInTheDocument();
    // The mark for a value local processes can read stays.
    const groq = screen.getByText("key").closest("tr")!;
    expect(within(groq).getByLabelText("Readable by local processes")).toBeInTheDocument();
    // The full reference stays one hover away, and copyable.
    fireEvent.click(within(row).getByRole("button", { name: `Actions for ${JIRA.ref}` }));
    expect(
      screen.getByRole("menuitem", { name: `Copy reference (${JIRA.ref})` }),
    ).toBeInTheDocument();
  });

  test("Used by names the first two users and +N, and the popover finds and scrolls", async () => {
    const many = ref({
      ref: "secret/shared",
      uri: "coffer://secret/shared",
      cited_by: [
        { kind: "mcp_server", name: "github", uid: "g" },
        { kind: "provider", name: "OpenAI", uid: "o" },
        ...Array.from({ length: 6 }, (_, i) => ({
          kind: "skill",
          name: `skill-${i}`,
          uid: `s${i}`,
        })),
      ],
    });
    api.list.mockResolvedValue({ refs: [many] });
    renderPage();
    const trigger = await screen.findByRole("button", { name: /is used by 8 things/ });
    expect(trigger).toHaveTextContent("github, OpenAI");
    expect(trigger).toHaveTextContent("+6");
    expect(trigger.textContent).not.toMatch(/^8/);
    fireEvent.click(trigger);
    // The type blocks come in order: Model provider first, then MCP server, then Skills.
    const find = await screen.findByRole("textbox", { name: "Find…" });
    expect(find).toHaveFocus();
    const rows = screen.getAllByRole("link").map((l) => l.textContent);
    expect(rows[0]).toContain("OpenAI");
    expect(rows[1]).toContain("github");
    fireEvent.change(find, { target: { value: "skill-3" } });
    expect(screen.getAllByRole("link")).toHaveLength(1);
    fireEvent.change(find, { target: { value: "mcp" } });
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  test("the status segments have no counts and narrow the list", async () => {
    renderPage();
    await screen.findByText("key");
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "In use" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not used" }));
    expect(names()).toEqual(["old-a", "old-b"]);
    expect(where()).toBe("/secrets?status=unused");
    // No Waiting / Refused segments, no type dropdown, no by-owner view.
    expect(screen.queryByRole("button", { name: /Waiting|Refused/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "By owner" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete unused/ })).not.toBeInTheDocument();
  });

  test("no match offers Clear filters, which resets the search and the status", async () => {
    renderPage("/secrets?status=unused&q=nothing-here");
    expect(await screen.findByText("No secret matches this search.")).toBeInTheDocument();
    const clears = screen.getAllByRole("button", { name: "Clear filters" });
    fireEvent.click(clears[clears.length - 1]);
    expect(where()).toBe("/secrets");
    expect(await screen.findByText("key")).toBeInTheDocument();
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
    const row = (await screen.findByText("key")).closest("tr")!;
    expect(await within(row).findByText("Waiting for approval")).toBeInTheDocument();
    expect(names()[0]).toBe("key");
    expect(screen.queryByText("Refused")).not.toBeInTheDocument();
  });

  test("search and status come from the URL", async () => {
    renderPage("/secrets?status=inUse&q=o");
    await screen.findByText("key");
    expect((screen.getByRole("textbox", { name: "Find a secret" }) as HTMLInputElement).value).toBe(
      "o",
    );
    // "o" matches a secret's name or the name of what uses it; unused ones are out.
    expect(names()).toEqual(["JIRA_PERSONAL_TOKEN", "key"]);
  });

  test("only time columns sort, in three clicks, and the sort stays in the URL", async () => {
    renderPage();
    await screen.findByText("key");
    // Names never sort.
    expect(screen.queryByRole("button", { name: "Name" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Used by" })).not.toBeInTheDocument();
    const lastUsed = () => screen.getByRole("button", { name: "Last used" });
    expect(names().slice(-2)).toEqual(["old-a", "old-b"]);
    fireEvent.click(lastUsed());
    expect(where()).toBe("/secrets?sort=last_used");
    expect(names().slice(0, 2)).toEqual(["old-b", "old-a"]);
    fireEvent.click(lastUsed());
    expect(where()).toBe("/secrets?sort=last_used%3Aasc");
    expect(names().slice(0, 2)).toEqual(["old-a", "old-b"]);
    fireEvent.click(lastUsed());
    expect(where()).toBe("/secrets");
    fireEvent.click(screen.getByRole("button", { name: "Created" }));
    expect(where()).toBe("/secrets?sort=created");
    // Newest first: the two oldest are last.
    expect(names().slice(-2)).toEqual(["old-b", "old-a"]);
  });

  test("a thousand secrets render in batches while search covers all of them", async () => {
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
    expect(screen.queryByText(/^Showing/)).toBeNull();
  });

  test("the header box selects every secret the filters show, and the bar reads N of M", async () => {
    renderPage();
    await screen.findByText("key");
    // The checkbox column is always first, the header box is the select-all.
    const first = screen.getAllByRole("row")[0];
    expect(within(first).getAllByRole("checkbox")).toHaveLength(1);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-a" }));
    const bar = screen.getByRole("region", { name: "Selected secrets" });
    expect(bar).toHaveTextContent("1 of 5 selected");
    expect(screen.queryByRole("textbox", { name: "Find a secret" })).not.toBeInTheDocument();
    expect(within(bar).queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all secrets" }));
    expect(bar).toHaveTextContent("5 of 5 selected");
    // Esc clears the selection and brings the filters back.
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("textbox", { name: "Find a secret" })).toBeInTheDocument();
  });

  test("a bulk delete skips and names what is in use, and deletes only the rest", async () => {
    renderPage();
    await screen.findByText("key");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-a" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select key" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select old-b" }));
    const bar = screen.getByRole("region", { name: "Selected secrets" });
    // A secret in use does not turn Delete off: the confirmation names it and skips it.
    const del = within(bar).getByRole("button", { name: "Delete…" });
    expect(del).toBeEnabled();
    fireEvent.click(del);
    const dialog = await screen.findByRole("dialog", { name: "Delete 3 secrets?" });
    expect(dialog).toHaveTextContent("old-a and old-b");
    expect(dialog).toHaveTextContent("key is in use and will be skipped.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 secrets" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledTimes(2));
    expect(api.remove).toHaveBeenCalledWith("secret/old-a");
    expect(api.remove).toHaveBeenCalledWith("secret/old-b");
    expect(api.remove).not.toHaveBeenCalledWith(GROQ.ref);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
