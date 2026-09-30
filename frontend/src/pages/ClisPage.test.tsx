// src/pages/ClisPage.test.tsx — the CLIs list: problems first, the Homebrew confirmation, Check again.
//
// Real QueryClientProvider; only the api module is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { Cli, CliInstall } from "@/lib/api/clis";
import { GCLOUD_LOGGED_OUT, GH_OUTDATED, JQ_MISSING, UV_READY, cli } from "@/test/cliFixtures";
import { ClisPage } from "./ClisPage";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    get: vi.fn(),
    check: vi.fn(),
    install: vi.fn(),
    installStatus: vi.fn(),
  },
}));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);

function listOf(items: Cli[]) {
  return { items, warnings: [] };
}

function Where() {
  const { pathname } = useLocation();
  return <div data-testid="where">{pathname}</div>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/clis"]}>
          <Routes>
            <Route path="/clis" element={<ClisPage />} />
            <Route path="*" element={null} />
          </Routes>
          <Where />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** The data rows, in order, by their first cell's command. */
function commands(): string[] {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map(
      (row) => within(row).getAllByRole("cell")[0].querySelector(".font-mono")?.textContent ?? "",
    );
}

function rowOf(command: string): HTMLElement {
  const row = screen
    .getAllByRole("row")
    .find((r) => r.querySelector(".font-mono")?.textContent === command);
  if (!row) throw new Error(`no row for ${command}`);
  return row;
}

beforeEach(() => {
  // The daemon's order: missing, outdated, logged out, ready.
  api.list.mockResolvedValue(listOf([JQ_MISSING, GH_OUTDATED, GCLOUD_LOGGED_OUT, UV_READY]));
});
afterEach(() => vi.clearAllMocks());

describe("ClisPage", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "the CLIs page lists problems first"
  test("the CLIs page lists problems first", async () => {
    renderPage();
    await screen.findByText("jq");
    expect(commands()).toEqual(["jq", "gh", "gcloud", "uv"]);

    const gh = rowOf("gh");
    expect(within(gh).getByText("2.30.0")).toBeInTheDocument();
    expect(within(gh).getByText("needs ≥ 2.40")).toBeInTheDocument();
    expect(within(gh).getByText("2 skills")).toBeInTheDocument();
    expect(within(gh).getByText("Too old")).toBeInTheDocument();

    const gcloud = rowOf("gcloud");
    expect(within(gcloud).getAllByText("Not logged in")).toHaveLength(2); // login + status
    expect(within(gcloud).getByRole("button", { name: "Copy login command" })).toBeInTheDocument();

    expect(within(rowOf("jq")).getByText("Not on PATH")).toBeInTheDocument();
    expect(within(rowOf("uv")).getByText("Ready")).toBeInTheDocument();

    expect(screen.getByTestId("clis-summary")).toHaveTextContent(
      /1 not found.*1 too old.*1 not logged in.*1 ready.*Checked/,
    );

    fireEvent.click(within(rowOf("gh")).getAllByRole("cell")[0]);
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/gh");
  });

  // scenario (web-ui, revise-web-ui-ia 7.14d): "installing a CLI asks first and uses Homebrew only"
  test("installing a CLI asks first and uses Homebrew only", async () => {
    const running: CliInstall = {
      command: "jq",
      formula: "jq",
      action: "install",
      argv: ["brew", "install", "jq"],
      state: "running",
      exit_code: null,
      started_at: new Date().toISOString(),
      finished_at: null,
      first_line: 0,
      lines: ["==> Fetching jq"],
      next_line: 1,
    };
    api.install.mockResolvedValue(running);
    api.installStatus.mockResolvedValue({
      ...running,
      state: "succeeded",
      exit_code: 0,
      finished_at: new Date().toISOString(),
      first_line: 1,
      lines: ["==> Pouring jq"],
      next_line: 2,
    });
    renderPage();
    await screen.findByText("jq");

    // The only installer offered anywhere on the page is the Homebrew one.
    const installButtons = screen.getAllByRole("button", { name: /^(Install…|Update…)$/ });
    expect(installButtons).toHaveLength(2); // jq (missing) and gh (outdated)

    fireEvent.click(within(rowOf("jq")).getByRole("button", { name: "Install…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Install jq?")).toBeInTheDocument();
    expect(within(dialog).getByTestId("cli-install-command")).toHaveTextContent("brew install jq");
    expect(within(dialog).getByText("Homebrew")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/2 skills need jq ≥ 1.6: gh-triage, log-digest/),
    ).toBeInTheDocument();
    // Nothing has run yet.
    expect(api.install).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Run brew install jq" }));
    await waitFor(() => expect(api.install).toHaveBeenCalledWith("jq", "jq"));
    const output = await within(dialog).findByLabelText("Install output");
    expect(output).toHaveTextContent("==> Fetching jq");
    // The poll asks from the next unseen line, then the job ends and the list refreshes.
    await waitFor(() => expect(api.installStatus).toHaveBeenCalledWith("jq", 1), { timeout: 3000 });
    await waitFor(() => expect(output).toHaveTextContent("==> Pouring jq"));
    expect(within(dialog).getByText(/Done \(exit code 0\)/)).toBeInTheDocument();
    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(1));
  });

  test("cancel runs nothing", async () => {
    renderPage();
    await screen.findByText("jq");
    fireEvent.click(within(rowOf("gh")).getByRole("button", { name: "Update…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Update gh?")).toBeInTheDocument();
    expect(within(dialog).getByTestId("cli-install-command")).toHaveTextContent("brew upgrade gh");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.install).not.toHaveBeenCalled();
  });

  test("Check again re-probes every command and shows the fresh answer", async () => {
    api.checkAll.mockResolvedValue(
      listOf([
        {
          ...GCLOUD_LOGGED_OUT,
          status: "ready",
          login: { ...GCLOUD_LOGGED_OUT.login, state: "logged_in" },
        },
      ]),
    );
    renderPage();
    await screen.findByText("jq");
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.checkAll).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("jq")).toBeNull());
    expect(within(rowOf("gcloud")).getByText("Logged in")).toBeInTheDocument();
  });

  test("no skill declares requires: shows the empty state with the docs link", async () => {
    api.list.mockResolvedValue({
      items: [],
      warnings: [{ skill_uid: "sk-x", skill_name: "x", message: "entry 1 is not understood" }],
    });
    renderPage();
    expect(await screen.findByText("No skill requires a command yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /How to declare requires:/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/guides/clis"),
    );
    expect(screen.getByText("x: entry 1 is not understood")).toBeInTheDocument();
  });

  test("a row with nothing to install offers no install button", async () => {
    api.list.mockResolvedValue(listOf([cli({ command: "sh", status: "missing", path: null })]));
    renderPage();
    await screen.findByText("sh");
    expect(within(rowOf("sh")).queryByRole("button")).toBeNull();
  });
});
