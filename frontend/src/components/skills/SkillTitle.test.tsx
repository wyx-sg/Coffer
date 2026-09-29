// frontend/src/components/skills/SkillTitle.test.tsx
//
// A skill's title (spec web-ui "Show and edit a title on MCP server and skill
// pages"): cleared on the detail page through the title dialog, after which the
// header and the list show the skill's name again — and the page still marks
// that name as fixed, because it is the folder agents load the skill from.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SkillDetailPage } from "@/pages/SkillDetailPage";
import type { SkillOut } from "@/lib/api/skills";
import { SkillsTable } from "./SkillsTable";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkill: vi.fn(),
  useRemoveSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSkillFiles: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useSkillFileContent: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
}));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: { scope: null, supports_scope: true } })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));

const { getApiClient } = await import("@/lib/api/client");
const skillHooks = await import("@/lib/hooks/useSkills");

const skill = (over: Partial<SkillOut> = {}): SkillOut => ({
  uid: "sk-7f1c",
  name: "pr-review",
  title: "Review a pull request",
  description: "Reviews a PR",
  source: { type: "local_import", original_path: "/tmp/pr-review" },
  builtin: false,
  enabled: true,
  scope: null,
  version_hash: "deadbeefcafe1234",
  master_path: "/master/pr-review",
  last_synced_from_source_at: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  bindings: [],
  ...over,
});

function mockSkill(s: SkillOut) {
  vi.mocked(skillHooks.useSkill).mockReturnValue({
    data: s,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof skillHooks.useSkill>);
}

function wrap(ui: React.ReactNode, path = "/skills/sk-7f1c") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/skills/:uid" element={ui} />
            <Route path="/skills" element={ui} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

afterEach(() => vi.clearAllMocks());

describe("skill title", () => {
  acceptance("web-ui", "clearing a skill's title shows its name again", async () => {
    const patch = vi.fn().mockResolvedValue({
      data: { ...skill(), title: null },
      error: undefined,
    });
    vi.mocked(getApiClient).mockReturnValue({ PATCH: patch } as unknown as ReturnType<
      typeof getApiClient
    >);

    // The header shows the title with the name beside it, and marks the name fixed.
    mockSkill(skill());
    const { unmount } = render(wrap(<SkillDetailPage />));
    const heading = screen.getByRole("heading", { level: 1 });
    expect(within(heading).getByText("Review a pull request")).toBeInTheDocument();
    expect(within(heading).getByText("pr-review")).toBeInTheDocument();
    expect(screen.getByText("Fixed name")).toBeInTheDocument();

    // The user clears the title; the name is shown read-only in the form.
    fireEvent.click(screen.getByRole("button", { name: /edit title/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("group", { name: /^name$/i })).toHaveTextContent("pr-review");
    expect(within(dialog).queryByRole("textbox", { name: /^name$/i })).not.toBeInTheDocument();
    const field = within(dialog).getByLabelText("Title");
    expect(field).toHaveValue("Review a pull request");
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch.mock.calls[0][1].params.path.uid).toBe("sk-7f1c");
    expect(patch.mock.calls[0][1].body).toEqual({ title: null });
    unmount();

    // With the title gone the header shows the name alone — still marked fixed.
    const cleared = skill({ title: null });
    mockSkill(cleared);
    const { unmount: unmountDetail } = render(wrap(<SkillDetailPage />));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/^pr-review$/);
    expect(screen.getByText("Fixed name")).toBeInTheDocument();
    unmountDetail();

    // And the list row names it by its name.
    render(wrap(<SkillsTable skills={[cleared]} />, "/skills"));
    const row = screen.getByText("pr-review").closest("tr") as HTMLElement;
    expect(within(row).queryByText("Review a pull request")).not.toBeInTheDocument();
  });

  test("the list's search matches a titled skill by its name", () => {
    render(wrap(<SkillsTable skills={[skill()]} />, "/skills"));
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "pr-rev" } });
    const row = screen.getByText("Review a pull request").closest("tr") as HTMLElement;
    expect(within(row).getByText("pr-review")).toBeInTheDocument();
  });
});
