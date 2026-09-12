// frontend/src/components/agents/AgentSkillsTab.test.tsx
//
// The Skills tab mirrors the MCP servers tab: it manages nothing, because
// delivery has one control and it lives on the skill (enabled + scope), not on
// the agent. Covered here:
//   - the "Managed by Coffer" pointer row renders and navigates to /skills
//   - the retired delivered-skills table is gone: no list of delivered skills,
//     no search box — the Skills page the row points at is where they live
//   - none of the retired controls survive: no follow switch, no Install
//     button, no per-row toggle, no status filter
//   - the unmanaged-skills section: hidden when empty, rows with location /
//     foreign-link badges and invalid reasons, adopt (disabled w/ hint when
//     invalid or foreign), open-folder and delete-with-confirm actions
//   - en/zh key parity for agents.skillsTab
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentSkillsTab } from "./AgentSkillsTab";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut, UnmanagedSkillOut } from "@/lib/api/agents";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

// The open-folder action goes through useFsActions → fsApi.open (the loopback
// daemon); mock the wire layer, like the agents API below.
vi.mock("@/lib/api/fs", () => ({
  fsApi: { open: vi.fn(), reveal: vi.fn() },
}));

// useUnmanagedSkills / adopt / delete run as REAL react-query hooks against
// this mocked wire layer.
vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    unmanagedSkills: vi.fn(),
    adoptUnmanagedSkill: vi.fn(),
    deleteUnmanagedSkill: vi.fn(),
  },
}));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const { fsApi } = await import("@/lib/api/fs");
const fs = vi.mocked(fsApi);

const AGENT: AgentOut = {
  name: "cc",
  type: "claude_code",
  config_dir: "/x",
  description: null,
  created_at: "",
  updated_at: "",
};

const UNMANAGED_GOOD: UnmanagedSkillOut = {
  name: "good",
  path: "/x/skills/good",
  location: "skills",
  valid: true,
  reason: null,
  foreign_link: false,
};

const UNMANAGED_INVALID: UnmanagedSkillOut = {
  name: "broken",
  path: "/x/skills/broken",
  location: "skills",
  valid: false,
  reason: "missing SKILL.md frontmatter",
  foreign_link: false,
};

const UNMANAGED_FOREIGN: UnmanagedSkillOut = {
  name: "linked",
  path: "/home/u/.agents/skills/linked",
  location: "agents_dir",
  valid: true,
  reason: null,
  foreign_link: true,
};

function stub(unmanaged: UnmanagedSkillOut[] = []) {
  api.unmanagedSkills.mockResolvedValue({ items: unmanaged });
  api.adoptUnmanagedSkill.mockResolvedValue({ name: "good" });
  api.deleteUnmanagedSkill.mockResolvedValue(undefined);
  fs.open.mockResolvedValue(undefined);
}

afterEach(() => vi.clearAllMocks());

function renderTab(agent: AgentOut = AGENT) {
  // The unmanaged section's bulk actions run via useBulkMutate, which reads the
  // QueryClient — provide one.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // ToastProvider is mounted so failure toasts (e.g. a failed open-folder)
  // actually render instead of hitting useToast's no-op fallback.
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <AgentSkillsTab agent={agent} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("AgentSkillsTab", () => {
  test("does not list the delivered skills — the Skills page holds them", async () => {
    stub([]);
    renderTab();

    // The read-only table (and its search box) is retired: it decided nothing
    // and duplicated the Skills page this tab already links to. With the
    // unmanaged section empty too, the tab carries no table at all.
    await waitFor(() => expect(api.unmanagedSkills).toHaveBeenCalledWith("cc"));
    expect(screen.queryByPlaceholderText(en.skills.searchPlaceholder)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  test("the managed header points at the Skills page and navigates there", () => {
    stub();
    renderTab();

    const header = screen.getByTestId("skills-managed-header");
    expect(within(header).getByText(en.agents.cofferManaged)).toBeInTheDocument();
    expect(within(header).getByText(en.agents.skillsTab.managedHint)).toBeInTheDocument();

    fireEvent.click(
      within(header).getByRole("button", { name: en.agents.skillsTab.openSkillsPage }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/skills");
  });

  test("carries no delivery control: no follow switch, install button or per-row toggle", () => {
    stub();
    renderTab();

    // Delivery is decided on the skill (enabled + scope), so the tab holds no
    // switch at all — not the retired follow switch, not a per-row binding one.
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /install/i })).not.toBeInTheDocument();
    // No status filter either.
    expect(
      screen.queryByRole("combobox", { name: en.resources.cols.status }),
    ).not.toBeInTheDocument();
  });

  describe("unmanaged skills", () => {
    test("section is hidden when the list is empty", async () => {
      stub([]);
      renderTab();

      // Let the unmanaged query settle, then assert absence.
      await waitFor(() => expect(api.unmanagedSkills).toHaveBeenCalledWith("cc"));
      expect(screen.queryByTestId("unmanaged-skills")).not.toBeInTheDocument();
    });

    test("rows render with location badges, invalid reason, and foreign-link badge", async () => {
      stub([UNMANAGED_GOOD, UNMANAGED_INVALID, UNMANAGED_FOREIGN]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      expect(within(section).getByText("good")).toBeInTheDocument();
      expect(within(section).getByText("broken")).toBeInTheDocument();
      expect(within(section).getByText("linked")).toBeInTheDocument();

      // Location badges.
      expect(within(section).getAllByText(en.agents.skillsTab.locationSkills).length).toBe(2);
      expect(within(section).getByText(en.agents.skillsTab.locationAgentsDir)).toBeInTheDocument();

      // Invalid reason surfaced as muted text.
      expect(within(section).getByText("missing SKILL.md frontmatter")).toBeInTheDocument();

      // Foreign symlink badge only on the foreign row.
      expect(within(section).getAllByTestId("foreign-link-badge")).toHaveLength(1);
    });

    test("adopt is disabled with a hint for invalid and foreign skills, enabled otherwise", async () => {
      stub([UNMANAGED_GOOD, UNMANAGED_INVALID, UNMANAGED_FOREIGN]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      const adoptButtons = within(section).getAllByRole("button", {
        name: en.agents.skillsTab.adopt,
      });
      expect(adoptButtons).toHaveLength(3);
      const [good, invalid, foreign] = adoptButtons;
      expect(good).toBeEnabled();
      expect(invalid).toBeDisabled();
      expect(foreign).toBeDisabled();

      // Disabled-reason tooltips live on the wrapper span.
      expect(
        within(section).getByTitle(en.agents.skillsTab.adoptDisabledInvalid),
      ).toBeInTheDocument();
      expect(
        within(section).getByTitle(en.agents.skillsTab.adoptDisabledForeign),
      ).toBeInTheDocument();
    });

    test("open folder asks the daemon to open the skill's path with the OS default", async () => {
      stub([UNMANAGED_GOOD]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      fireEvent.click(
        within(section).getByRole("button", { name: en.agents.skillsTab.openFolder }),
      );
      // Empty `withApp` → no `with` on the wire, so the OS picks the handler
      // (the file manager, for a directory).
      await waitFor(() => expect(fs.open).toHaveBeenCalledWith("/x/skills/good", undefined));
    });

    test("a failed open surfaces an error toast", async () => {
      stub([UNMANAGED_GOOD]);
      fs.open.mockRejectedValue(new Error("nope"));
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      fireEvent.click(
        within(section).getByRole("button", { name: en.agents.skillsTab.openFolder }),
      );
      expect(await screen.findByText(en.agents.skillsTab.openFolderFailed)).toBeInTheDocument();
    });

    test("adopt calls the API with the skill name and location", async () => {
      stub([UNMANAGED_GOOD]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      fireEvent.click(within(section).getByRole("button", { name: en.agents.skillsTab.adopt }));
      await waitFor(() =>
        expect(api.adoptUnmanagedSkill).toHaveBeenCalledWith("cc", "good", "skills"),
      );
    });

    test("delete asks for confirmation, then calls the API with the location", async () => {
      stub([UNMANAGED_FOREIGN]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      fireEvent.click(within(section).getByRole("button", { name: en.common.delete }));

      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText(en.agents.skillsTab.deleteConfirm)).toBeInTheDocument();
      expect(api.deleteUnmanagedSkill).not.toHaveBeenCalled();

      fireEvent.click(within(dialog).getByRole("button", { name: en.common.delete }));
      await waitFor(() =>
        expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("cc", "linked", "agents_dir"),
      );
    });

    test("bulk adopt only adopts eligible rows (skips invalid/foreign)", async () => {
      stub([UNMANAGED_GOOD, UNMANAGED_FOREIGN]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      // Select all rows, then trigger the bulk Adopt from the bulk bar.
      fireEvent.click(within(section).getByRole("checkbox", { name: en.common.bulk.selectAll }));
      const bar = screen.getByText(/2 selected/i).closest("div")!;
      fireEvent.click(within(bar).getByRole("button", { name: en.agents.skillsTab.adopt }));

      await waitFor(() =>
        expect(api.adoptUnmanagedSkill).toHaveBeenCalledWith("cc", "good", "skills"),
      );
      // The foreign-link row is never adopted, so exactly one call fires.
      expect(api.adoptUnmanagedSkill).toHaveBeenCalledTimes(1);
    });

    test("bulk delete confirms, then deletes every selected row", async () => {
      stub([UNMANAGED_GOOD, UNMANAGED_FOREIGN]);
      renderTab();

      const section = await screen.findByTestId("unmanaged-skills");
      fireEvent.click(within(section).getByRole("checkbox", { name: en.common.bulk.selectAll }));
      const bar = screen.getByText(/2 selected/i).closest("div")!;
      fireEvent.click(within(bar).getByRole("button", { name: en.common.bulk.delete }));

      const dialog = await screen.findByRole("dialog");
      expect(api.deleteUnmanagedSkill).not.toHaveBeenCalled();
      fireEvent.click(within(dialog).getByRole("button", { name: en.common.delete }));

      await waitFor(() =>
        expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("cc", "good", "skills"),
      );
      expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("cc", "linked", "agents_dir");
      expect(api.deleteUnmanagedSkill).toHaveBeenCalledTimes(2);
    });
  });

  test("en and zh locales carry the same agents.skillsTab keys", () => {
    const enKeys = Object.keys(en.agents.skillsTab).sort();
    const zhKeys = Object.keys(zh.agents.skillsTab).sort();
    expect(zhKeys).toEqual(enKeys);
    for (const key of [
      "managedHint",
      "unmanagedTitle",
      "adopt",
      "adoptDisabledInvalid",
      "adoptDisabledForeign",
      "deleteConfirm",
      "foreignLink",
      "locationSkills",
      "locationAgentsDir",
      "adoptSuccess",
      "openFolder",
      "openFolderFailed",
      "openSkillsPage",
    ]) {
      expect(enKeys).toContain(key);
    }
  });
});
