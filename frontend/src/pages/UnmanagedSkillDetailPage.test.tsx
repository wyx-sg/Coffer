// src/pages/UnmanagedSkillDetailPage.test.tsx — one unmanaged skill folder, at /agents/:type/skills/unmanaged/:location/:name.
//
// One unmanaged skill's detail page (spec skill-manager "Preview an unmanaged
// skill read-only"; boards 2.1.57, 2.1.58): the standard detail header (the
// name in mono, an "Unmanaged" pill, the meta line, Adopt as the one button and
// a ⋯ with only Delete…), the Overview as property rows, an invalid folder's
// reason shown up front, the Files tab's tree + read-only viewer, and the two
// header actions — adopt (the Adopt dialog) and delete (then back to the
// agent's Skills tab).
//
// The hooks run for real against a mocked wire layer (agentsApi); the fs actions
// are mocked at their hook. The page is addressed by the agent's TYPE; the REST
// reads by its uid (`u-cc`), found through the per-type listing.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { UnmanagedSkillDetailPage } from "./UnmanagedSkillDetailPage";
import { ToastProvider } from "@/components/ui/toast";
import type { UnmanagedSkillDetailOut } from "@/lib/api/agents-workspace";
import type { SkillFileNode } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import en from "@/i18n/locales/en.json";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    types: vi.fn(),
    get: vi.fn(),
    unmanagedSkill: vi.fn(),
    unmanagedSkillFiles: vi.fn(),
    unmanagedSkillFileContent: vi.fn(),
    adoptUnmanagedSkill: vi.fn(),
    deleteUnmanagedSkill: vi.fn(),
  },
}));

vi.mock("@/lib/hooks/useSkills", () => ({ useSkills: () => ({ data: [] }) }));

const openMock = vi.fn<(path: string, withApp: string) => Promise<void>>(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: vi.fn(() => Promise.resolve()) }),
}));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const GOOD: UnmanagedSkillDetailOut = {
  name: "loose",
  path: "/home/u/.claude/skills/loose",
  location: "skills",
  valid: true,
  reason: null,
  foreign_link: false,
  description: "Does loose things.",
};

const TREE: SkillFileNode = {
  name: "loose",
  path: "",
  abs_path: "/home/u/.claude/skills/loose",
  folder_abs_path: "/home/u/.claude/skills",
  type: "dir",
  size: null,
  truncated: false,
  children: [
    {
      name: "SKILL.md",
      path: "SKILL.md",
      abs_path: "/home/u/.claude/skills/loose/SKILL.md",
      folder_abs_path: "/home/u/.claude/skills/loose",
      type: "file",
      size: 30,
      truncated: false,
      children: [],
    },
  ],
};

function stub(skill: UnmanagedSkillDetailOut = GOOD) {
  api.types.mockResolvedValue({
    types: [{ type: "claude_code", uid: "u-cc" }],
  } as Awaited<ReturnType<typeof agentsApi.types>>);
  api.get.mockResolvedValue({ uid: "u-cc", name: "cc", type: "claude_code" } as Awaited<
    ReturnType<typeof agentsApi.get>
  >);
  api.unmanagedSkill.mockResolvedValue(skill);
  api.unmanagedSkillFiles.mockResolvedValue({ root: TREE });
  api.unmanagedSkillFileContent.mockResolvedValue({
    path: "SKILL.md",
    abs_path: "/home/u/.claude/skills/loose/SKILL.md",
    folder_abs_path: "/home/u/.claude/skills/loose",
    content: "# Loose skill body",
    truncated: false,
    binary: false,
    size: 30,
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
          initialEntries={[`/agents/claude_code/skills/unmanaged/${location}/${name}${search}`]}
        >
          <Routes>
            <Route
              path="/agents/:type/skills/unmanaged/:location/:name"
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
  test("the header names the skill in mono, with an Unmanaged pill and the meta line", async () => {
    stub();
    renderAt();

    expect(await screen.findByRole("heading", { name: "loose" })).toBeInTheDocument();
    expect(screen.getByText(en.agents.skillsTab.unmanagedBadge)).toBeInTheDocument();
    expect(
      await screen.findByText("Claude Code’s own skill · ~/.claude/skills/loose · 1 file"),
    ).toBeInTheDocument();
    // No back link and no location badges in the header.
    expect(screen.queryByRole("link", { name: /skills/i })).not.toBeInTheDocument();
    expect(api.unmanagedSkill).toHaveBeenCalledWith("u-cc", "loose", "skills");
  });

  test("the overview is property rows: description, folder, found in, files", async () => {
    stub();
    renderAt();
    expect(await screen.findByText("Does loose things.")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("~/.claude/skills/loose")).toBeInTheDocument();
    expect(screen.getByText("Claude Code’s skills directory")).toBeInTheDocument();
    expect(await screen.findByText("SKILL.md")).toBeInTheDocument();
    expect(screen.getByText(/coffer reads this folder but doesn’t manage it/i)).toBeInTheDocument();
  });

  acceptance(
    "skill-manager",
    "open an unmanaged skill's detail page from the agent's Skills tab",
    async () => {
      stub();
      renderAt("?tab=files");

      // The tree, then a file's read-only viewer — SKILL.md opens first, no Edit.
      fireEvent.click(await screen.findByRole("treeitem", { name: "SKILL.md" }));
      expect(await screen.findByText("Loose skill body")).toBeInTheDocument();
      expect(api.unmanagedSkillFileContent).toHaveBeenCalledWith(
        "u-cc",
        "loose",
        "skills",
        "SKILL.md",
      );
      expect(screen.getByText("~/.claude/skills/loose/SKILL.md")).toBeInTheDocument();
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

    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("SKILL.md is missing")).toBeInTheDocument();
    // Adopt is left out for a folder that cannot be adopted.
    expect(
      screen.queryByRole("button", { name: en.agents.skillsTab.adopt }),
    ).not.toBeInTheDocument();
  });

  test("the ⋯ holds only Delete…", async () => {
    stub();
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: /^More for/ }));
    expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Delete…"]);
  });

  acceptance(
    "skill-manager",
    "adopt or delete an unmanaged skill from its detail page",
    async () => {
      // Adopt: the primary button opens the Adopt dialog for this folder.
      stub();
      const first = renderAt();
      fireEvent.click(await screen.findByRole("button", { name: en.agents.skillsTab.adopt }));
      expect(await screen.findByRole("dialog", { name: "Adopt loose" })).toBeInTheDocument();
      first.unmount();

      // Delete: confirm, then back to the agent's Skills tab.
      stub();
      renderAt();
      fireEvent.click(await screen.findByRole("button", { name: /^More for/ }));
      fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
      const dialog = await screen.findByRole("dialog");
      expect(api.deleteUnmanagedSkill).not.toHaveBeenCalled();
      fireEvent.click(within(dialog).getByRole("button", { name: en.common.delete }));
      await waitFor(() =>
        expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("u-cc", "loose", "skills"),
      );
      expect(await screen.findByTestId("where")).toHaveTextContent("/agents/claude_code/skills");
    },
  );

  test("a folder the scan no longer finds shows a not-found state with the way back", async () => {
    stub();
    api.unmanagedSkill.mockRejectedValue(new Error("gone"));
    renderAt();
    expect(
      await screen.findByText(en.agents.skillsTab.unmanagedDetail.notFound),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skills" })).toHaveAttribute(
      "href",
      "/agents/claude_code/skills",
    );
  });
});
