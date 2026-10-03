// src/components/skills/SkillRequiresTab.test.tsx — a skill's Requires tab lists what its SKILL.md declares, in four groups.
//
// Commands · Secrets · Tools · Skills. Each row is name · state · a link to the
// page that owns the thing; no install or login step of its own and no
// hand-off in a row (that is one button in the banner above the tabs). Real
// QueryClientProvider; only the api module is mocked.
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
  more: Partial<SkillOut> = {},
) {
  const skill = {
    uid: skillUid,
    requires: requires.map((command) => ({ command, min_version: null })),
    requires_secrets: requiresSecrets,
    requires_tools: [],
    requires_skills: [],
    ...more,
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
      expect(links.map((a) => a.getAttribute("href"))).toEqual([`/clis/${command}`]);
      expect(within(rows[i]).getByRole("link", { name: "View in CLIs" })).toBeInTheDocument();
    }

    fireEvent.click(within(rows[1]).getByRole("link", { name: "View in CLIs" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/gcloud");
  });

  acceptance(
    "web-ui",
    "the requires tab checks the commands again and keeps the hand-off out of its rows",
    async () => {
      api.list.mockResolvedValue({ items: [JQ_MISSING, GCLOUD_LOGGED_OUT], warnings: [] });
      api.checkAll.mockResolvedValue({ items: [JQ_MISSING, GCLOUD_LOGGED_OUT], warnings: [] });
      renderTab("sk-gh-triage", ["jq", "gcloud"]);
      await screen.findByText("Not installed");
      expect(screen.queryByRole("button", { name: /Install/ })).toBeNull();
      expect(screen.queryByRole("button", { name: "Copy prompt" })).toBeNull();
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
      expect(within(set).getByRole("link", { name: "View in Secrets" })).toBeInTheDocument();
      expect(within(missing).getByText("secret NPM_TOKEN is not set")).toBeInTheDocument();
      // A person's task: a link to Secrets, no hand-off prompt, no command.
      expect(within(section).queryByRole("button", { name: "Copy prompt" })).toBeNull();
      expect(within(section).queryByText(/coffer /)).toBeNull();
      fireEvent.click(within(missing).getByRole("link", { name: "View in Secrets" }));
      expect(screen.getByTestId("where")).toHaveTextContent("/secrets");
    },
  );

  test("a skill that declares only secrets lists them without an empty state", async () => {
    api.list.mockResolvedValue({ items: [], warnings: [] });
    renderTab("sk-secrets-only", [], [{ name: "API_KEY", is_set: false }]);
    expect(await screen.findByText("secret API_KEY is not set")).toBeInTheDocument();
    expect(screen.queryByText("Nothing required")).toBeNull();
  });

  test("tools show their kind and state, with a link to the page that owns them", async () => {
    api.list.mockResolvedValue({ items: [], warnings: [] });
    renderTab("sk-tools", [], [], {
      requires_tools: [
        { name: "github", uid: "t-1", kind: "mcp_server", status: "off", why: null },
        { name: "billing-api", uid: "t-2", kind: "custom_tools", status: "failing", why: "401" },
        { name: "linear", uid: "t-3", kind: "mcp_server", status: "healthy", why: null },
      ],
    });
    const section = await screen.findByTestId("skill-requires-tools");
    const [off, failing, healthy] = within(section).getAllByRole("listitem");
    expect(off).toHaveTextContent("githubMCP serverOff");
    expect(within(off).getByRole("link", { name: "View in MCP servers" })).toHaveAttribute(
      "href",
      "/mcp-servers/github",
    );
    expect(failing).toHaveTextContent("Custom tools");
    expect(failing).toHaveTextContent("Failing");
    expect(within(failing).getByRole("link", { name: "View in Custom tools" })).toHaveAttribute(
      "href",
      "/custom-tools/billing-api",
    );
    expect(healthy).toHaveTextContent("Healthy");
  });

  test("skills it loads say whether they reach the same agents", async () => {
    api.list.mockResolvedValue({ items: [], warnings: [] });
    renderTab("sk-skills", [], [], {
      requires_skills: [
        {
          name: "coffer-evidence",
          uid: "s-1",
          found: true,
          delivered_to_same_agents: true,
          missing_agent_names: [],
        },
        {
          name: "writer",
          uid: "s-2",
          found: true,
          delivered_to_same_agents: false,
          missing_agent_names: ["Codex"],
        },
        {
          name: "ghost",
          uid: null,
          found: false,
          delivered_to_same_agents: false,
          missing_agent_names: [],
        },
      ],
    });
    const section = await screen.findByTestId("skill-requires-skills");
    const [ok, partial, gone] = within(section).getAllByRole("listitem");
    expect(ok).toHaveTextContent("Delivered to the same agents");
    expect(within(ok).getByRole("link", { name: "View in Skills" })).toHaveAttribute(
      "href",
      "/skills/coffer-evidence",
    );
    expect(partial).toHaveTextContent("Not delivered to Codex");
    expect(gone).toHaveTextContent("Not in your library");
    expect(within(gone).queryByRole("link")).toBeNull();
  });

  test("a skill that declares nothing says so", async () => {
    api.list.mockResolvedValue({ items: [UV_READY], warnings: [] });
    renderTab("sk-nothing", []);
    expect(await screen.findByText("Nothing required")).toBeInTheDocument();
  });
});
