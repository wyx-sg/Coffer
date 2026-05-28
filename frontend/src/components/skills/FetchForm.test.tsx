// frontend/src/components/skills/FetchForm.test.tsx — TEST21-013
//
// Form renders + submits via `useFetchSkill`; the error message renders
// via `translateApiError` when the mutation surfaces an error.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { FetchForm } from "./FetchForm";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useSkills", () => ({
  useFetchSkill: vi.fn(),
}));
const { useFetchSkill } = await import("@/lib/hooks/useSkills");
const useFetchSkillMock = vi.mocked(useFetchSkill);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

describe("FetchForm", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders inputs + cancel/fetch buttons", () => {
    useFetchSkillMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useFetchSkill>);
    render(<FetchForm onClose={() => {}} onSuccess={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    // Submit button uses the "Fetch from Git" label (skills.fetch).
    expect(screen.getByRole("button", { name: /fetch from git/i })).toBeInTheDocument();
  });

  test("submits the form body and fires onSuccess on resolve", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onSuccess = vi.fn();
    useFetchSkillMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useFetchSkill>);
    render(<FetchForm onClose={() => {}} onSuccess={onSuccess} />, {
      wrapper: wrap(null),
    });
    const urlInput = screen.getByPlaceholderText(/github.com/i) as HTMLInputElement;
    fireEvent.change(urlInput, { target: { value: "https://example.com/repo" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch from git/i }));
    await new Promise((r) => setTimeout(r, 0));
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    const body = mutateAsync.mock.calls[0][0];
    expect(body.git_url).toBe("https://example.com/repo");
    expect(body.git_ref).toBe("main"); // default
    expect(onSuccess).toHaveBeenCalled();
  });

  test("Cancel triggers onClose", () => {
    useFetchSkillMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useFetchSkill>);
    const onClose = vi.fn();
    render(<FetchForm onClose={onClose} onSuccess={() => {}} />, {
      wrapper: wrap(null),
    });
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  test("renders the error text when the mutation surfaces an error", () => {
    useFetchSkillMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: new ApiError("SSRF_BLOCKED", "blocked: 127.0.0.1"),
    } as unknown as ReturnType<typeof useFetchSkill>);
    render(<FetchForm onClose={() => {}} onSuccess={() => {}} />, {
      wrapper: wrap(null),
    });
    // translateApiError stays on-message even when the i18n key is missing.
    expect(screen.getByText(/blocked|ssrf/i)).toBeInTheDocument();
  });
});
