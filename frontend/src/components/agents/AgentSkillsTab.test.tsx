// frontend/src/components/agents/AgentSkillsTab.test.tsx
//
// The Skills tab's "Managed by Coffer" section lists every skill that has a
// binding for THIS agent, each with an enable/disable Switch reflecting the
// binding's enabled state. (AgentInstallSkillsDialog also reads useSkills, so
// the single mock below covers both.)
//
// Spec 005 FR-025 additions covered here:
//   - the "Follow master library" switch reflects agent.follow_all_skills and
//     PATCHes the agent on toggle
//   - while following, per-skill switches edit skill_exclusions (PATCH) and do
//     NOT call the binding enable/disable mutations
//   - while NOT following, per-skill switches keep the old binding behaviour
//   - the unmanaged-skills section: hidden when empty, rows with location /
//     foreign-link badges and invalid reasons, adopt (disabled w/ hint when
//     invalid or foreign) and delete-with-confirm actions
//   - en/zh key parity for agents.skillsTab
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentSkillsTab } from "./AgentSkillsTab";
import type { AgentOut, UnmanagedSkillOut } from "@/lib/api/agents";
import type { LinkMode } from "@/lib/api/skills";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

const useSkillsMock = vi.fn();
const enableMutate = vi.fn();
const disableMutate = vi.fn();

function mockBinding(linkMode: LinkMode | null) {
  return {
    data: [
      {
        name: "hello",
        description: "hi",
        bindings: [
          {
            agent_name: "cc",
            enabled: true,
            last_linked_at: null,
            last_link_path: null,
            link_mode: linkMode,
          },
        ],
      },
      // A skill not bound to this agent must NOT appear in the section.
      { name: "other", description: "", bindings: [] },
    ],
    isPending: false,
    error: null,
  };
}

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: () => useSkillsMock(),
  useEnableSkill: () => ({ mutate: enableMutate, isPending: false }),
  useDisableSkill: () => ({ mutate: disableMutate, isPending: false }),
}));

// usePatchAgent / useUnmanagedSkills / adopt / delete run as REAL react-query
// hooks against this mocked wire layer.
vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    patch: vi.fn(),
    unmanagedSkills: vi.fn(),
    adoptUnmanagedSkill: vi.fn(),
    deleteUnmanagedSkill: vi.fn(),
  },
}));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const AGENT: AgentOut = {
  name: "cc",
  type: "claude_code",
  config_dir: "/x",
  description: null,
  created_at: "",
  updated_at: "",
  follow_all_skills: false,
  skill_exclusions: [],
};

const FOLLOW_AGENT: AgentOut = { ...AGENT, follow_all_skills: true };

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
  useSkillsMock.mockReturnValue(mockBinding(null));
  api.unmanagedSkills.mockResolvedValue({ items: unmanaged });
  api.patch.mockResolvedValue(AGENT);
  api.adoptUnmanagedSkill.mockResolvedValue({ name: "good" });
  api.deleteUnmanagedSkill.mockResolvedValue(undefined);
}

afterEach(() => vi.clearAllMocks());

function renderTab(agent: AgentOut = AGENT) {
  // AgentInstallSkillsDialog + AgentSkillsBulkActions now run via useBulkMutate,
  // which reads the QueryClient — provide one even though no bulk op fires here.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentSkillsTab agent={agent} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The per-skill binding switch for the "hello" fixture skill. */
const helloSwitch = () =>
  screen.getByRole("switch", { name: en.agents.skillsTab.toggleAria.replace("{{name}}", "hello") });
const followSwitch = () => screen.getByRole("switch", { name: en.agents.skillsTab.follow });

describe("AgentSkillsTab", () => {
  test("lists the skill bound to this agent with a toggle switch", () => {
    stub();
    renderTab();

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByText("other")).not.toBeInTheDocument();

    expect(helloSwitch()).toBeChecked();
  });

  test("shows a degraded warning chip when the binding fell back to a copy", () => {
    // FR-012: when symlink/junction delivery isn't available Coffer copies the
    // skill instead; the UI MUST surface that the binding is degraded.
    stub();
    useSkillsMock.mockReturnValue(mockBinding("copy_fallback"));
    renderTab();

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByTestId("skill-degraded-badge")).toBeInTheDocument();
  });

  test("does NOT show the degraded chip for a normal symlink binding", () => {
    stub();
    useSkillsMock.mockReturnValue(mockBinding("symlink"));
    renderTab();

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByTestId("skill-degraded-badge")).not.toBeInTheDocument();
  });

  describe("follow master library", () => {
    test("switch reflects follow_all_skills=false and PATCHes true on toggle", async () => {
      stub();
      renderTab(AGENT);

      const sw = followSwitch();
      expect(sw).not.toBeChecked();
      fireEvent.click(sw);
      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith("cc", { follow_all_skills: true }),
      );
    });

    test("switch reflects follow_all_skills=true and PATCHes false on toggle", async () => {
      stub();
      renderTab(FOLLOW_AGENT);

      const sw = followSwitch();
      expect(sw).toBeChecked();
      fireEvent.click(sw);
      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith("cc", { follow_all_skills: false }),
      );
    });

    test("treats missing follow_all_skills as not following", () => {
      stub();
      const legacy = { ...AGENT };
      delete legacy.follow_all_skills;
      delete legacy.skill_exclusions;
      renderTab(legacy);
      expect(followSwitch()).not.toBeChecked();
    });

    test("in follow mode, switching a skill OFF patches skill_exclusions and does NOT touch the binding", async () => {
      stub();
      renderTab(FOLLOW_AGENT);

      const sw = helloSwitch();
      expect(sw).toBeChecked(); // not excluded
      fireEvent.click(sw);
      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith("cc", { skill_exclusions: ["hello"] }),
      );
      expect(enableMutate).not.toHaveBeenCalled();
      expect(disableMutate).not.toHaveBeenCalled();
    });

    test("in follow mode, an excluded skill renders OFF and switching it ON removes the exclusion", async () => {
      stub();
      renderTab({ ...FOLLOW_AGENT, skill_exclusions: ["hello", "keep"] });

      const sw = helloSwitch();
      expect(sw).not.toBeChecked();
      fireEvent.click(sw);
      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith("cc", { skill_exclusions: ["keep"] }),
      );
      expect(enableMutate).not.toHaveBeenCalled();
    });

    test("when NOT following, the per-skill switch keeps the old binding behaviour", () => {
      stub();
      renderTab(AGENT);

      fireEvent.click(helloSwitch()); // enabled → disable
      expect(disableMutate).toHaveBeenCalledWith({ name: "hello", body: { agent_name: "cc" } });
      expect(api.patch).not.toHaveBeenCalled();
    });
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
      expect(
        within(section).getAllByText(en.agents.skillsTab.locationSkills).length,
      ).toBe(2);
      expect(
        within(section).getByText(en.agents.skillsTab.locationAgentsDir),
      ).toBeInTheDocument();

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
      expect(
        within(dialog).getByText(en.agents.skillsTab.deleteConfirm),
      ).toBeInTheDocument();
      expect(api.deleteUnmanagedSkill).not.toHaveBeenCalled();

      fireEvent.click(within(dialog).getByRole("button", { name: en.common.delete }));
      await waitFor(() =>
        expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("cc", "linked", "agents_dir"),
      );
    });
  });

  test("en and zh locales carry the same agents.skillsTab keys", () => {
    const enKeys = Object.keys(en.agents.skillsTab).sort();
    const zhKeys = Object.keys(zh.agents.skillsTab).sort();
    expect(zhKeys).toEqual(enKeys);
    for (const key of [
      "follow",
      "followHint",
      "excludeHint",
      "unmanagedTitle",
      "adopt",
      "adoptDisabledInvalid",
      "adoptDisabledForeign",
      "deleteConfirm",
      "foreignLink",
      "locationSkills",
      "locationAgentsDir",
      "adoptSuccess",
    ]) {
      expect(enKeys).toContain(key);
    }
  });
});
