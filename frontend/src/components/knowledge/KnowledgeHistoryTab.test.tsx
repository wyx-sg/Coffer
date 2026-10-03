// A document's History tab on its own (boards 5.1.05, 5.1.07, 5.1.08): one
// bordered list whose rows open in place into a diff with Restore this version,
// the one Load-error row when the history cannot be read, and the neutral
// "History needs git" row carrying the daemon's install prompt.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { KnowledgeHistoryTab } from "@/components/knowledge/KnowledgeHistoryTab";
import { wrapLine } from "@/lib/knowledge/wrapLine";
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
  test("is one list; a row opens in place into its diff and Restore", async () => {
    api.getHistory.mockResolvedValue({ path: GATEWAY.path, versions });
    api.restoreVersion.mockResolvedValue(GATEWAY);
    renderTab();

    expect(await screen.findAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("newest first")).toBeNull();
    expect(screen.queryByText(/\d versions?$/)).toBeNull();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(api.getVersionDiff).not.toHaveBeenCalled();

    const row = screen.getByRole("button", { name: /^You/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
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

  test("the current version offers no restore; a curation row links to the pass", async () => {
    api.getHistory.mockResolvedValue({ path: GATEWAY.path, versions: [versions[0]] });
    renderTab();
    expect(await screen.findByRole("link", { name: "See the pass" })).toHaveAttribute(
      "href",
      `/knowledge/changes/${PASS.version}`,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Curation/ }));
    expect(
      await screen.findByRole("button", { name: "Changes in this version" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore this version" })).toBeNull();
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
