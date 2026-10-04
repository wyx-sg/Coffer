// A document's History tab on its own (boards 5.1.05, 5.1.07, 5.1.08): one
// card whose left list picks a version and whose right pane shows its diff with
// Restore this version (the newest, current version chosen to begin with), the one Load-error row when the history cannot be read, and the neutral
// "History needs git" row carrying the daemon's install prompt.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { KnowledgeHistoryTab } from "@/components/knowledge/KnowledgeHistoryTab";
import { wrapLine } from "@/lib/diff/wrapLine";
import { EDIT, GATEWAY, NAME, PASS } from "@/components/knowledge/knowledgeTestData";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/api/knowledge", () => ({
  getHistory: vi.fn(),
  getVersionDiff: vi.fn(),
  getVersionBody: vi.fn(),
  restoreVersion: vi.fn(),
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const older = { ...EDIT, version: "c0ffee01", collections: [NAME] };
const versions = [
  { change: PASS, removed: false },
  { change: older, removed: false },
];

function renderTab() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter>
            <KnowledgeHistoryTab path={GATEWAY.path} currentBody="# Account Gateway\n\nNew." />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  api.getVersionDiff.mockResolvedValue({
    path: GATEWAY.path,
    version: "c0ffee01",
    added: 1,
    removed: 1,
    status: "modified",
    diff: "@@ -1,2 +1,2 @@\n # Account Gateway\n-The old layer.\n+The orchestration layer.\n",
  });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("the version list", () => {
  test("is a list beside the diff; choosing a row shows its diff and Restore", async () => {
    api.getHistory.mockResolvedValue({ path: GATEWAY.path, versions });
    api.restoreVersion.mockResolvedValue(GATEWAY);
    renderTab();

    const list = await screen.findByRole("list", { name: "Versions" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Current")).toBeInTheDocument();
    // The current version is chosen to begin with: no restore onto itself.
    expect(screen.getByRole("button", { name: /^Curation/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.queryByRole("button", { name: "Restore this version" })).toBeNull();

    const row = screen.getByRole("button", { name: /^You/ });
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-current", "true");
    await waitFor(() => expect(api.getVersionDiff).toHaveBeenCalledWith(GATEWAY.path, "c0ffee01"));
    expect(await screen.findByText("The orchestration layer.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore this version" }));
    await waitFor(() =>
      expect(api.restoreVersion).toHaveBeenCalledWith({ path: GATEWAY.path, version: "c0ffee01" }),
    );
    expect(await screen.findByText("Restored as a new version")).toBeInTheDocument();
  });

  test("Compare with current sets a version against the document as it is now", async () => {
    api.getHistory.mockResolvedValue({ path: GATEWAY.path, versions });
    api.getVersionBody.mockResolvedValue({
      path: GATEWAY.path,
      version: "c0ffee01",
      body: "# Account Gateway\n\nThe old layer.",
    });
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /^You/ }));
    fireEvent.click(screen.getByRole("button", { name: "Compare with current" }));
    await waitFor(() => expect(api.getVersionBody).toHaveBeenCalledWith(GATEWAY.path, "c0ffee01"));
    expect(await screen.findByText("The old layer.")).toBeInTheDocument();
  });

  test("the current version offers no restore; a curation version keeps its label with no pass link", async () => {
    api.getHistory.mockResolvedValue({ path: GATEWAY.path, versions: [versions[0]] });
    renderTab();
    expect(await screen.findByRole("button", { name: /^Curation/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "See the pass" })).toBeNull();
    expect(
      await screen.findByRole("button", { name: "Changes in this version" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore this version" })).toBeNull();
  });

  test("the divider can be dragged below the width the list opens at", async () => {
    api.getHistory.mockResolvedValue({ path: GATEWAY.path, versions });
    renderTab();
    const sep = await screen.findByRole("separator", { name: "Resize the list" });
    expect(sep).toHaveAttribute("aria-valuenow", "250");
    sep.focus();
    for (let i = 0; i < 4; i++) fireEvent.keyDown(sep, { key: "ArrowLeft" });
    expect(Number(sep.getAttribute("aria-valuenow"))).toBeLessThan(240);
  });
});

describe("a history that cannot be read", () => {
  test("is one Load-error row with Open Activity and Retry", async () => {
    api.getHistory.mockRejectedValue(new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "lock held"));
    renderTab();
    expect(await screen.findByText("Couldn’t read this document’s history")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Activity" })).toHaveAttribute(
      "href",
      "/activity",
    );
    const before = api.getHistory.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.getHistory.mock.calls.length).toBe(before + 1));
  });

  test("with git missing it is the neutral row: Check again and the install prompt", async () => {
    api.getHistory.mockRejectedValue(
      new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git", {
        reason: "git_missing",
        handoff: { prompt: "Please install git on this machine." },
      }),
    );
    renderTab();
    expect(await screen.findByText("History needs git")).toBeInTheDocument();
    expect(
      screen.getByText("Install git on this Mac to see versions. The document itself is fine."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open Activity" })).toBeNull();
    const before = api.getHistory.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.getHistory.mock.calls.length).toBe(before + 1));
    fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith("Please install git on this machine.");
  });
});

describe("long diff lines", () => {
  test("wrap at a word with an indented continuation, never cut off", () => {
    const line = "word ".repeat(40).trim();
    const rows = wrapLine(line, 40);
    expect(rows.length).toBeGreaterThan(1);
    expect(rows.every((r) => r.length <= 40)).toBe(true);
    expect(rows[1].startsWith("  ")).toBe(true);
    expect(rows.map((r) => r.trim()).join(" ")).toBe(line);
    expect(wrapLine("short")).toEqual(["short"]);
  });
});
