// src/components/skills/SkillRequiresTab.test.tsx — a skill's Requires tab lists what its SKILL.md declares.
//
// One row per command — name · state · the hand-off to an agent when the command
// needs the person · Open in CLIs — and no install or login step of its own.
// Real QueryClientProvider;
// only the api module is mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { GCLOUD_LOGGED_OUT, JQ_MISSING, UV_READY, cli } from "@/test/cliFixtures";
import { acceptance } from "@/test/acceptance";
import type { SkillOut } from "@/lib/api/skills";

import { SkillRequiresTab } from "./SkillRequiresTab";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    get: vi.fn(),
    check: vi.fn(),
  },
}));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderTab(skillUid = "sk-gh-triage", requires = ["jq", "gcloud", "uv"]) {
  const skill = {
    uid: skillUid,
    requires: requires.map((command) => ({ command, min_version: null })),
  } as SkillOut;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/skills/gh-triage/requires"]}>
        <Routes>
          <Route path="/skills/:name/:tab" element={<SkillRequiresTab skill={skill} />} />
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

    await screen.findByText("Not installed");
    expect(screen.getByText("Not logged in")).toBeInTheDocument();
    expect(screen.getByText(/^Found/)).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(screen.queryByText("docker")).toBeNull();
    for (const [i, command] of ["jq", "gcloud", "uv"].entries()) {
      const links = within(rows[i]).getAllByRole("link");
      expect(links.map((a) => a.getAttribute("href"))).toEqual([
        `/clis/${command}`,
        `/clis/${command}`,
      ]);
      expect(within(rows[i]).getByRole("link", { name: /Open in CLIs/ })).toBeInTheDocument();
    }
    expect(screen.getByText(/Hand a command that needs you to your agent/)).toBeInTheDocument();

    fireEvent.click(within(rows[1]).getByRole("link", { name: "gcloud" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/gcloud");
  });

  acceptance("web-ui", "the requires tab links to the CLIs page and hands a command to an agent", async () => {
    api.list.mockResolvedValue({ items: [JQ_MISSING, GCLOUD_LOGGED_OUT], warnings: [] });
    api.checkAll.mockResolvedValue({ items: [JQ_MISSING, GCLOUD_LOGGED_OUT], warnings: [] });
    renderTab("sk-gh-triage", ["jq", "gcloud"]);
    await screen.findByText("Not installed");
    expect(screen.queryByRole("button", { name: /Install/ })).toBeNull();
    expect(screen.getAllByRole("button", { name: "Copy prompt" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("gcloud auth login")).toBeNull();
    expect(screen.queryByText(/brew/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.checkAll).toHaveBeenCalledTimes(1));
  });

  test("a skill that declares nothing says so", async () => {
    api.list.mockResolvedValue({ items: [UV_READY], warnings: [] });
    renderTab("sk-nothing", []);
    expect(await screen.findByText("No commands required")).toBeInTheDocument();
  });
});
