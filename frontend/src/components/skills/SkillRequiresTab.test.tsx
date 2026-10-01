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

function renderTab(
  skillUid = "sk-gh-triage",
  requires = ["jq", "gcloud", "uv"],
  requiresSecrets: SkillOut["requires_secrets"] = [],
) {
  const skill = {
    uid: skillUid,
    requires: requires.map((command) => ({ command, min_version: null })),
    requires_secrets: requiresSecrets,
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
  acceptance("web-ui", "a skill's requirement links to its CLI", async () => {
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

  acceptance(
    "web-ui",
    "the requires tab links to the CLIs page and hands a command to an agent",
    async () => {
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
    },
  );

  acceptance(
    "web-ui",
    "the requires tab lists a skill's secrets and opens Secrets for a missing one",
    async () => {
      api.list.mockResolvedValue({ items: [JQ_MISSING], warnings: [] });
      renderTab(
        "sk-gh-triage",
        ["jq"],
        [
          { name: "GITHUB_TOKEN", is_set: true },
          { name: "NPM_TOKEN", is_set: false },
        ],
      );
      await screen.findByText("Not installed");
      const section = screen.getByTestId("skill-requires-secrets");
      const [set, missing] = within(section).getAllByRole("listitem");
      expect(within(set).getByText("GITHUB_TOKEN")).toBeInTheDocument();
      expect(within(set).getByText("Set")).toBeInTheDocument();
      expect(within(set).queryByRole("link")).toBeNull();
      expect(within(missing).getByText("secret NPM_TOKEN is not set")).toBeInTheDocument();
      // A person's task: a link to Secrets, no hand-off prompt, no command.
      expect(within(section).queryByRole("button", { name: "Copy prompt" })).toBeNull();
      expect(within(section).queryByText(/coffer /)).toBeNull();
      fireEvent.click(within(missing).getByRole("link", { name: /Open Secrets/ }));
      expect(screen.getByTestId("where")).toHaveTextContent("/secrets");
    },
  );

  test("a skill that declares only secrets lists them without an empty state", async () => {
    api.list.mockResolvedValue({ items: [], warnings: [] });
    renderTab("sk-secrets-only", [], [{ name: "API_KEY", is_set: false }]);
    expect(await screen.findByText("secret API_KEY is not set")).toBeInTheDocument();
    expect(screen.queryByText("Nothing required")).toBeNull();
  });

  test("a skill that declares nothing says so", async () => {
    api.list.mockResolvedValue({ items: [UV_READY], warnings: [] });
    renderTab("sk-nothing", []);
    expect(await screen.findByText("Nothing required")).toBeInTheDocument();
  });
});
