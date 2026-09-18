// frontend/src/pages/SkillDetailPage.test.tsx
//
// The per-skill detail page: header (name + source badge + Delete) and two
// tabs — Overview, Files. We mock the skill hooks so the page doesn't depend
// on a running daemon.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SkillDetailPage } from "./SkillDetailPage";
import type { SkillOut } from "@/lib/api/skills";

vi.mock("@/lib/hooks/useSkills", () => ({
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
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: disableMutate, isPending: false })),
}));

const skillHooks = await import("@/lib/hooks/useSkills");
const useSkillMock = vi.mocked(skillHooks.useSkill);

// Both identities, kept apart: the uid is what the route carries and what the
// disable below is addressed to, "hello" is only the heading.
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
  useSkillMock.mockReturnValue({
    data: skill,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof skillHooks.useSkill>);
}

function renderAt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/skills/${SKILL_UID}`]}>
        <Routes>
          <Route path="/skills/:uid" element={<SkillDetailPage />} />
          <Route path="/skills" element={<div>skills list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

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

  // spec skill-manager FR-030: the read model carries an explicit `builtin`
  // flag "rather than leaving each client to infer it from the source variant".
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
});
