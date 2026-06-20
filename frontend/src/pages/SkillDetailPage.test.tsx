// frontend/src/pages/SkillDetailPage.test.tsx
//
// The per-skill detail page: header (name + source badge + Delete) and two
// tabs — Overview, Files. We mock the skill hooks so the page doesn't depend
// on a running daemon.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

const skillHooks = await import("@/lib/hooks/useSkills");
const useSkillMock = vi.mocked(skillHooks.useSkill);

const LOCAL_SKILL: SkillOut = {
  name: "hello",
  description: "a greeting",
  source: { type: "local_import", original_path: "/tmp/hello" },
  enabled: true,
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
  test("renders the header, source badge, and the two tabs", () => {
    mockSkill(LOCAL_SKILL);
    renderAt();
    expect(screen.getByRole("heading", { name: "hello" })).toBeInTheDocument();
    expect(screen.getByText("local_import")).toBeInTheDocument();
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
