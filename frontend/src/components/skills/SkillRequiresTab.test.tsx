// src/components/skills/SkillRequiresTab.test.tsx — a skill's Requires tab lists what its SKILL.md declares.
//
// Real QueryClientProvider; only the api module is mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { GCLOUD_LOGGED_OUT, JQ_MISSING, UV_READY, cli } from "@/test/cliFixtures";
import { SkillRequiresTab } from "./SkillRequiresTab";

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

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderTab(skillUid = "sk-gh-triage") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/skills/gh-triage/requires"]}>
        <Routes>
          <Route path="/skills/:name/:tab" element={<SkillRequiresTab skillUid={skillUid} />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("SkillRequiresTab", () => {
  // scenario (web-ui, revise-web-ui-ia 7.14d): "a skill's requirement links to its CLI"
  test("a skill's requirement links to its CLI", async () => {
    const other = cli({
      command: "docker",
      needed_by: [{ skill_uid: "sk-other", skill_name: "other", min_version: null, why: null }],
    });
    api.list.mockResolvedValue({
      items: [JQ_MISSING, GCLOUD_LOGGED_OUT, UV_READY, other],
      warnings: [],
    });
    renderTab();

    const list = await screen.findByRole("list", { name: "Requires" });
    const links = within(list).getAllByRole("link");
    // Only this skill's commands, each opening its page on the CLIs page.
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/clis/jq",
      "/clis/gcloud",
      "/clis/uv",
    ]);
    expect(screen.queryByText("docker")).toBeNull();

    expect(
      screen.getByText(/Not on PATH\. The skill filters issue JSON with it\./),
    ).toBeInTheDocument();
    expect(screen.getByText("uv 0.4.18 · /opt/homebrew/bin/uv")).toBeInTheDocument();
    expect(within(list).getByText("gcloud auth login")).toBeInTheDocument();
    expect(
      screen.getByText(/The skill is still delivered\..*needs jq until it is installed\./),
    ).toBeInTheDocument();

    fireEvent.click(within(list).getByRole("link", { name: "gcloud" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/gcloud");
  });

  test("Install… opens the same confirmation, and Check again re-probes", async () => {
    api.list.mockResolvedValue({ items: [JQ_MISSING], warnings: [] });
    api.checkAll.mockResolvedValue({
      items: [{ ...JQ_MISSING, status: "ready", path: "/opt/homebrew/bin/jq", version: "1.7" }],
      warnings: [],
    });
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Install…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("cli-install-command")).toHaveTextContent("brew install jq");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(api.install).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.checkAll).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("jq 1.7 · /opt/homebrew/bin/jq")).toBeInTheDocument();
    expect(screen.queryByText(/The skill is still delivered/)).toBeNull();
  });

  test("a skill that declares nothing says so", async () => {
    api.list.mockResolvedValue({ items: [UV_READY], warnings: [] });
    renderTab("sk-nothing");
    expect(
      await screen.findByText("This skill declares no required commands."),
    ).toBeInTheDocument();
  });
});
