// frontend/src/components/skills/SkillTable.test.tsx — TEST21-013
//
// Renders rows, handles the destructive Delete confirm path.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { SkillTable } from "./SkillTable";
import type { SkillOut } from "@/lib/api/skills";

vi.mock("@/lib/hooks/useSkills", () => ({
  useRemoveSkill: vi.fn(),
}));

const { useRemoveSkill } = await import("@/lib/hooks/useSkills");
const useRemoveSkillMock = vi.mocked(useRemoveSkill);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

const SKILLS: SkillOut[] = [
  {
    name: "hello",
    description: "hi",
    source: { type: "local_import", original_path: "/tmp/h" },
    enabled: true,
    version_hash: "deadbeef",
    master_path: "/master/hello",
    last_synced_from_source_at: null,
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    bindings: [
      {
        agent_name: "cur",
        enabled: true,
        last_linked_at: null,
        last_link_path: null,
        link_mode: "symlink",
      },
    ],
  },
  {
    name: "lonely",
    description: "no agents",
    source: {
      type: "git",
      git_url: "https://example.com/repo",
      git_ref: "main",
      git_subpath: "",
    },
    enabled: true,
    version_hash: "0",
    master_path: "/master/lonely",
    last_synced_from_source_at: null,
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    bindings: [],
  },
];

describe("SkillTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders one row per skill with source + binding cells", () => {
    useRemoveSkillMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    render(<SkillTable skills={SKILLS} />, { wrapper: wrap(null) });
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("lonely")).toBeInTheDocument();
    expect(screen.getByText("local_import")).toBeInTheDocument();
    expect(screen.getByText("git")).toBeInTheDocument();
    // The 'hello' row shows the cur+ binding text.
    expect(screen.getByText(/cur\+/)).toBeInTheDocument();
    // The 'lonely' row shows the em-dash placeholder.
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  test("Delete calls the remove mutation when the user confirms", () => {
    const mutate = vi.fn();
    useRemoveSkillMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<SkillTable skills={SKILLS} />, { wrapper: wrap(null) });
    const deletes = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deletes[0]);
    expect(confirmSpy).toHaveBeenCalled();
    expect(mutate).toHaveBeenCalledWith("hello");
    confirmSpy.mockRestore();
  });

  test("Delete is a no-op when the user cancels confirm", () => {
    const mutate = vi.fn();
    useRemoveSkillMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<SkillTable skills={SKILLS} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]);
    expect(mutate).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
