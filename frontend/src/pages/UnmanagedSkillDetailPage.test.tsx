// frontend/src/pages/UnmanagedSkillDetailPage.test.tsx
//
// One unmanaged skill's detail page (spec skill-manager "Preview an unmanaged
// skill read-only"): the header (name, unmanaged + location badges, a back link
// to the agent's Skills tab), the Overview (SKILL.md description, path), an
// invalid folder's reason shown up front, the Files tab's tree + read-only
// preview, and the three header actions — open folder, adopt (then on to the new
// managed skill), delete (then back to the agent's Skills tab).
//
// The hooks run for real against a mocked wire layer (agentsApi); the fs actions
// are mocked at their hook. The fixture agent's uid (`u-cc`) is deliberately not
// its name (`cc`), so every URL assertion has to spell the uid.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { UnmanagedSkillDetailPage } from "./UnmanagedSkillDetailPage";
import { ToastProvider } from "@/components/ui/toast";
import type { UnmanagedSkillDetailOut } from "@/lib/api/agents";
import type { SkillFileNode } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import en from "@/i18n/locales/en.json";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    get: vi.fn(),
    unmanagedSkill: vi.fn(),
    unmanagedSkillFiles: vi.fn(),
    unmanagedSkillFileContent: vi.fn(),
    adoptUnmanagedSkill: vi.fn(),
    deleteUnmanagedSkill: vi.fn(),
  },
}));

const openMock = vi.fn<(path: string, withApp: string) => Promise<void>>(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: vi.fn(() => Promise.resolve()) }),
}));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const GOOD: UnmanagedSkillDetailOut = {
  name: "loose",
  path: "/x/skills/loose",
  location: "skills",
  valid: true,
  reason: null,
  foreign_link: false,
  description: "Does loose things.",
};

const TREE: SkillFileNode = {
  name: "loose",
  path: "",
  abs_path: "/x/skills/loose",
  folder_abs_path: "/x/skills",
  type: "dir",
  size: null,
  truncated: false,
  children: [
    {
      name: "SKILL.md",
      path: "SKILL.md",
      abs_path: "/x/skills/loose/SKILL.md",
      folder_abs_path: "/x/skills/loose",
      type: "file",
      size: 30,
      truncated: false,
      children: [],
    },
  ],
};

function stub(skill: UnmanagedSkillDetailOut = GOOD) {
  api.get.mockResolvedValue({ uid: "u-cc", name: "cc" } as Awaited<
    ReturnType<typeof agentsApi.get>
  >);
  api.unmanagedSkill.mockResolvedValue(skill);
  api.unmanagedSkillFiles.mockResolvedValue({ root: TREE });
  api.unmanagedSkillFileContent.mockResolvedValue({
    path: "SKILL.md",
    abs_path: "/x/skills/loose/SKILL.md",
    folder_abs_path: "/x/skills/loose",
    content: "# Loose skill body",
    truncated: false,
    binary: false,
    size: 30,
    fingerprint: "f",
  });
  api.adoptUnmanagedSkill.mockResolvedValue({ uid: "u-new", name: "loose" });
  api.deleteUnmanagedSkill.mockResolvedValue(undefined);
}

afterEach(() => vi.clearAllMocks());

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{`${loc.pathname}${loc.search}`}</p>;
}

function renderAt(search = "", location = "skills", name = "loose") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter
          initialEntries={[`/agents/u-cc/skills/unmanaged/${location}/${name}${search}`]}
        >
          <Routes>
            <Route
              path="/agents/:uid/skills/unmanaged/:location/:name"
              element={<UnmanagedSkillDetailPage />}
            />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("UnmanagedSkillDetailPage", () => {
  test("the header names the skill, badges it unmanaged and links back to the Skills tab", async () => {
    stub();
    renderAt();

    expect(await screen.findByRole("heading", { name: "loose" })).toBeInTheDocument();
    expect(screen.getByTestId("unmanaged-badge")).toHaveTextContent(
      en.agents.skillsTab.unmanagedBadge,
    );
    // The location reads in the header badge and again in the Overview.
    expect(screen.getAllByText(en.agents.skillsTab.locationSkills)).toHaveLength(2);
    expect(api.unmanagedSkill).toHaveBeenCalledWith("u-cc", "loose", "skills");

    const back = await screen.findByRole("link", { name: /Back to cc/ });
    expect(back).toHaveAttribute("href", "/agents/u-cc?tab=skills");
    fireEvent.click(back);
    expect(await screen.findByTestId("where")).toHaveTextContent("/agents/u-cc?tab=skills");
  });

  test("the overview shows the SKILL.md description and the folder path", async () => {
    stub();
    renderAt();
    expect(await screen.findByText("Does loose things.")).toBeInTheDocument();
    expect(screen.getByText("/x/skills/loose")).toBeInTheDocument();
    expect(screen.queryByTestId("unmanaged-invalid")).not.toBeInTheDocument();
  });

  acceptance(
    "skill-manager",
    "open an unmanaged skill's detail page from the agent's Skills tab",
    async () => {
      stub();
      renderAt("?tab=files");

      // The tree, then a file's read-only preview — no Edit affordance.
      fireEvent.click(await screen.findByRole("button", { name: "SKILL.md" }));
      expect(await screen.findByText("Loose skill body")).toBeInTheDocument();
      expect(api.unmanagedSkillFileContent).toHaveBeenCalledWith(
        "u-cc",
        "loose",
        "skills",
        "SKILL.md",
      );
      expect(screen.queryByRole("button", { name: en.common.edit })).not.toBeInTheDocument();
    },
  );

  acceptance("skill-manager", "an invalid unmanaged skill still opens and says why", async () => {
    stub({
      ...GOOD,
      name: "broken",
      valid: false,
      reason: "SKILL.md is missing",
      description: null,
    });
    renderAt("", "skills", "broken");

    const notice = await screen.findByTestId("unmanaged-invalid");
    expect(within(notice).getByText("SKILL.md is missing")).toBeInTheDocument();
    const adopt = screen.getByRole("button", { name: en.agents.skillsTab.adopt });
    expect(adopt).toBeDisabled();
    expect(screen.getByTitle(en.agents.skillsTab.adoptDisabledInvalid)).toBeInTheDocument();
  });

  test("open folder asks the daemon to open the folder with the OS default", async () => {
    stub();
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: en.agents.skillsTab.openFolder }));
    await waitFor(() => expect(openMock).toHaveBeenCalledWith("/x/skills/loose", ""));
  });

  test("a failed open surfaces an error toast", async () => {
    stub();
    openMock.mockRejectedValueOnce(new Error("nope"));
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: en.agents.skillsTab.openFolder }));
    expect(await screen.findByText(en.agents.skillsTab.openFolderFailed)).toBeInTheDocument();
  });

  acceptance(
    "skill-manager",
    "adopt or delete an unmanaged skill from its detail page",
    async () => {
      // Adopt: on to the new managed skill's own page.
      stub();
      const first = renderAt();
      fireEvent.click(await screen.findByRole("button", { name: en.agents.skillsTab.adopt }));
      await waitFor(() =>
        expect(api.adoptUnmanagedSkill).toHaveBeenCalledWith("u-cc", "loose", "skills"),
      );
      expect(await screen.findByTestId("where")).toHaveTextContent("/skills/u-new");
      first.unmount();

      // Delete: confirm, then back to the agent's Skills tab.
      stub();
      renderAt();
      fireEvent.click(await screen.findByRole("button", { name: en.common.delete }));
      const dialog = await screen.findByRole("dialog");
      expect(api.deleteUnmanagedSkill).not.toHaveBeenCalled();
      fireEvent.click(within(dialog).getByRole("button", { name: en.common.delete }));
      await waitFor(() =>
        expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("u-cc", "loose", "skills"),
      );
      expect(await screen.findByTestId("where")).toHaveTextContent("/agents/u-cc?tab=skills");
    },
  );

  test("a folder the scan no longer finds shows a not-found state with the way back", async () => {
    stub();
    api.unmanagedSkill.mockRejectedValue(new Error("gone"));
    renderAt();
    expect(
      await screen.findByText(en.agents.skillsTab.unmanagedDetail.notFound),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to/ })).toHaveAttribute(
      "href",
      "/agents/u-cc?tab=skills",
    );
  });
});
