// frontend/src/components/skills/ImportForm.test.tsx — TEST21-013
//
// Form renders + submits via `useImportSkill`.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { ImportForm } from "./ImportForm";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useSkills", () => ({
  useImportSkill: vi.fn(),
}));
const { useImportSkill } = await import("@/lib/hooks/useSkills");
const useImportSkillMock = vi.mocked(useImportSkill);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

describe("ImportForm", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders path input + cancel/import buttons", () => {
    useImportSkillMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useImportSkill>);
    render(<ImportForm onClose={() => {}} onSuccess={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^import$/i })).toBeInTheDocument();
  });

  test("submits the path and fires onSuccess", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onSuccess = vi.fn();
    useImportSkillMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useImportSkill>);
    render(<ImportForm onClose={() => {}} onSuccess={onSuccess} />, {
      wrapper: wrap(null),
    });
    const pathInput = screen.getByPlaceholderText(/\.claude\/skills/i) as HTMLInputElement;
    fireEvent.change(pathInput, { target: { value: "/tmp/my-skill" } });
    fireEvent.click(screen.getByRole("button", { name: /^import$/i }));
    await new Promise((r) => setTimeout(r, 0));
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(mutateAsync.mock.calls[0][0]).toEqual({ path: "/tmp/my-skill" });
    expect(onSuccess).toHaveBeenCalled();
  });

  test("Cancel triggers onClose", () => {
    useImportSkillMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useImportSkill>);
    const onClose = vi.fn();
    render(<ImportForm onClose={onClose} onSuccess={() => {}} />, {
      wrapper: wrap(null),
    });
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  test("renders the error text when the mutation surfaces an error", () => {
    useImportSkillMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: new ApiError("INVALID_SKILL", "missing SKILL.md"),
    } as unknown as ReturnType<typeof useImportSkill>);
    render(<ImportForm onClose={() => {}} onSuccess={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByText(/missing SKILL\.md|invalid/i)).toBeInTheDocument();
  });
});
