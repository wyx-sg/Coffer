// frontend/src/pages/SkillDetailPage.test.tsx
//
// The per-skill detail page: header (name + source badge + Delete) and two
// tabs — Overview, Files. We mock the skill hooks so the page doesn't depend
// on a running daemon.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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

const LOCAL_SKILL: SkillOut = {
  name: "hello",
  description: "a greeting",
  source: { type: "local_import", original_path: "/tmp/hello" },
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
      <MemoryRouter initialEntries={["/skills/hello"]}>
        <Routes>
          <Route path="/skills/:name" element={<SkillDetailPage />} />
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
    // scope is null on this skill, so "Every agent" is the live segment.
    expect(screen.getByRole("button", { name: /every agent/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("the scope control's Disabled segment takes the skill out of service", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /^disabled$/i }));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "skill", name: "hello" });
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
