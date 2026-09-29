// frontend/src/pages/SkillDetailPage.test.tsx
//
// The per-skill detail page: header (name + source badge + Delete) and two
// tabs — Overview, Files. We mock the skill hooks so the page doesn't depend
// on a running daemon.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { SkillDetailPage } from "./SkillDetailPage";
import type { SkillOut } from "@/lib/api/skills";

// The page is addressed by the skill's NAME and resolves it to the uid against
// the skills list — `listed` is what that list holds.
let listed: SkillOut[] = [];
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({ data: listed, isPending: false, error: null })),
  useSkill: vi.fn(),
  useRemoveSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSkillFiles: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useSkillFileContent: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
}));

// The header's ScopeControl pulls its scope through hand-written fetch hooks
// and drives enable/disable — stub both so it renders without a daemon.
const { disableMutate } = vi.hoisted(() => ({ disableMutate: vi.fn() }));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: { scope: null, supports_scope: true } })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useSetResourceTitle: vi.fn(() => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn().mockResolvedValue({}),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: disableMutate, isPending: false })),
}));

const skillHooks = await import("@/lib/hooks/useSkills");
const useSkillMock = vi.mocked(skillHooks.useSkill);

// Both identities, kept apart: the name "hello" is what the route carries and
// the heading, the uid is what the disable below is addressed to.
const SKILL_UID = "sk-0a3e";

const LOCAL_SKILL: SkillOut = {
  uid: SKILL_UID,
  name: "hello",
  description: "a greeting",
  source: { type: "local_import", original_path: "/tmp/hello" },
  builtin: false,
  enabled: true,
  scope: null,
  version_hash: "deadbeefcafe1234",
  master_path: "/master/hello",
  last_synced_from_source_at: null,
  created_at: "2026-05-26T00:00:00Z",
  updated_at: "2026-05-26T00:00:00Z",
  bindings: [],
};

function mockSkill(skill: SkillOut) {
  listed = [skill];
  useSkillMock.mockReturnValue({
    data: skill,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof skillHooks.useSkill>);
}

/** Where the router is now — path and query — for the addressing tests. */
const where = { url: "" };
function Probe() {
  const loc = useLocation();
  where.url = loc.pathname + loc.search;
  return null;
}

/** Render `/skills/<key><suffix>`; the key defaults to the listed skill's name. */
function renderAt(suffix = "", key = listed[0]?.name ?? "hello") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/skills/${key}${suffix}`]}>
        <Routes>
          <Route
            path="/skills/:name/:tab?"
            element={
              <>
                <SkillDetailPage />
                <Probe />
              </>
            }
          />
          <Route path="/skills" element={<div>skills list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  listed = [LOCAL_SKILL];
});
listed = [LOCAL_SKILL];

describe("SkillDetailPage", () => {
  test("renders the header and the two tabs", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    expect(screen.getByRole("heading", { name: "hello" })).toBeInTheDocument();
    // The source badge is intentionally hidden in the header (every skill is
    // local_import today); source still surfaces in the Overview tab below.
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /bindings/i })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /files/i })).toBeInTheDocument();
    // Overview (default) shows the truncated version hash + local path.
    expect(screen.getByText("deadbeefcafe")).toBeInTheDocument();
    expect(screen.getByText("/tmp/hello")).toBeInTheDocument();
  });

  test("the Update button is never shown (local-import only)", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    expect(screen.queryByRole("button", { name: /^update$/i })).not.toBeInTheDocument();
  });

  test("mounts the scope control in the header, not a separate scope card", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    expect(screen.getByTestId("scope-control")).toBeInTheDocument();
    expect(screen.queryByTestId("scope-card")).not.toBeInTheDocument();
    // scope is null on this skill, so the one button reports "Every agent".
    expect(within(screen.getByTestId("scope-control")).getByRole("button")).toHaveTextContent(
      /every agent/i,
    );
  });

  test("the scope control's Disabled choice takes the skill out of service", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    fireEvent.click(within(screen.getByTestId("scope-control")).getByRole("button"));
    fireEvent.click(screen.getByRole("radio", { name: /^disabled$/i }));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "skill", uid: SKILL_UID });
  });

  // spec skill-manager "Mark the builtin skill on every surface": the read model carries an
  // explicit `builtin` flag "rather than leaving each client to infer it from the source variant".
  // The Overview tab used to branch on `source.type` while the table branched
  // on the flag — two answers to one question, free to disagree.
  test("Overview reads the builtin flag, not the source variant", () => {
    mockSkill({
      ...LOCAL_SKILL,
      name: "coffer-guide",
      builtin: true,
      source: { type: "builtin" },
    });
    renderAt();
    expect(screen.getByTestId("skill-detail-source")).toHaveTextContent(/generated by coffer/i);
  });

  // spec skill-manager "Regenerate Coffer's builtin skill from the build": an
  // edit to a builtin skill does not survive, and the surfaces MUST say so.
  // The page is where the flag lives, so it must reach the Files tab's viewer.
  test("the Files tab of a builtin skill is read-only and says why", () => {
    mockSkill({ ...LOCAL_SKILL, name: "coffer-guide", builtin: true, source: { type: "builtin" } });
    vi.mocked(skillHooks.useSkillFiles).mockReturnValue({
      data: {
        name: "coffer-guide",
        path: "",
        type: "dir",
        size: null,
        truncated: false,
        children: [
          {
            name: "SKILL.md",
            path: "SKILL.md",
            type: "file",
            size: 7,
            truncated: false,
            children: null,
          },
        ],
      },
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof skillHooks.useSkillFiles>);
    vi.mocked(skillHooks.useSkillFileContent).mockReturnValue({
      data: {
        path: "SKILL.md",
        abs_path: "/master/coffer-guide/SKILL.md",
        folder_abs_path: "/master/coffer-guide",
        content: "# Guide",
        truncated: false,
        binary: false,
        size: 7,
        fingerprint: "fp-1",
      },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof skillHooks.useSkillFileContent>);

    renderAt("/files");
    fireEvent.click(screen.getByRole("button", { name: "SKILL.md" }));

    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/rewrites it at every start/i)).toBeInTheDocument();
  });

  test("Overview shows the import path for a skill that is not Coffer's own", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    expect(screen.getByTestId("skill-detail-source")).toHaveTextContent("/tmp/hello");
  });

  test("shows the load-failed card when the skill fails to load", () => {
    useSkillMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: { code: "RESOURCE_NOT_FOUND", message: "nope" },
    } as unknown as ReturnType<typeof skillHooks.useSkill>);
    renderAt();
    expect(screen.getByText(/failed to load skills/i)).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "a detail tab lives in the path"
  test("the open tab lives in the path, under the skill's name", () => {
    mockSkill(LOCAL_SKILL);
    renderAt("/files");
    expect(screen.getByRole("tab", { name: /files/i })).toHaveAttribute("aria-selected", "true");
    // The REST reads still go by uid.
    expect(useSkillMock).toHaveBeenLastCalledWith(SKILL_UID);
    fireEvent.mouseDown(screen.getByRole("tab", { name: /overview/i }));
    expect(where.url).toBe("/skills/hello");
    fireEvent.mouseDown(screen.getByRole("tab", { name: /files/i }));
    expect(where.url).toBe("/skills/hello/files");
  });

  // revise-web-ui-ia: web-ui "an old query-tab address redirects to the path"
  test("an old ?tab=files address redirects to the path", async () => {
    mockSkill(LOCAL_SKILL);
    renderAt("?tab=files");
    await waitFor(() => expect(where.url).toBe("/skills/hello/files"));
    expect(screen.getByRole("tab", { name: /files/i })).toHaveAttribute("aria-selected", "true");
  });

  // revise-web-ui-ia: web-ui "an old uid address redirects to the name"
  test("an old uid address redirects to the name address, keeping the tab", async () => {
    mockSkill(LOCAL_SKILL);
    renderAt("?tab=files", SKILL_UID);
    await waitFor(() => expect(where.url).toBe("/skills/hello/files"));
    expect(screen.getByRole("heading", { name: "hello" })).toBeInTheDocument();
  });

  test("shows the loading state while the skills list loads", () => {
    vi.mocked(skillHooks.useSkills).mockReturnValueOnce({
      data: undefined,
      isPending: true,
      error: null,
    } as unknown as ReturnType<typeof skillHooks.useSkills>);
    useSkillMock.mockReturnValue({
      data: undefined,
      isPending: true,
      error: null,
    } as unknown as ReturnType<typeof skillHooks.useSkill>);
    renderAt();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("a name no skill has shows the load-failed card", () => {
    mockSkill(LOCAL_SKILL);
    useSkillMock.mockReturnValue({
      data: undefined,
      isPending: true,
      error: null,
    } as unknown as ReturnType<typeof skillHooks.useSkill>);
    renderAt("", "nope");
    expect(screen.getByText(/failed to load skills/i)).toBeInTheDocument();
    expect(useSkillMock).toHaveBeenLastCalledWith("");
  });
});
