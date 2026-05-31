// frontend/src/components/skills/SkillVerifyDialog.test.tsx
//
// The drift dialog must not flash a false "no drift detected" before the verify
// mutation actually runs (FE5): while the mutation is idle/pending (entries is
// an empty array but isSuccess is false), it shows the checking spinner — the OK
// branch is gated on verify.isSuccess.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SkillVerifyDialog } from "./SkillVerifyDialog";

vi.mock("@/lib/hooks/useSkills", () => ({ useVerifySkills: vi.fn() }));
const { useVerifySkills } = await import("@/lib/hooks/useSkills");
const useVerifySkillsMock = vi.mocked(useVerifySkills);

function stub(state: Record<string, unknown>) {
  useVerifySkillsMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    ...state,
  } as unknown as ReturnType<typeof useVerifySkills>);
}

afterEach(() => vi.clearAllMocks());

describe("SkillVerifyDialog", () => {
  test("does not show the OK state while the mutation is still idle/pending", () => {
    // Idle: empty entries but NOT yet successful — must show the spinner, never OK.
    stub({ data: { entries: [] }, isPending: false, isError: false, isSuccess: false });
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);

    expect(screen.getByText(/checking/i)).toBeInTheDocument();
    expect(screen.queryByText(/no drift/i)).not.toBeInTheDocument();
  });

  test("shows the OK state only once the verify mutation succeeds with no entries", () => {
    stub({ data: { entries: [] }, isPending: false, isError: false, isSuccess: true });
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);

    expect(screen.getByText(/no drift/i)).toBeInTheDocument();
    expect(screen.queryByText(/checking/i)).not.toBeInTheDocument();
  });

  test("lists drift entries once succeeded", () => {
    stub({
      data: {
        entries: [
          {
            skill_name: "hello",
            agent_name: "cc",
            kind: "missing_link",
            target_path: "/x",
            suggested_remedy: "re-link",
          },
        ],
      },
      isPending: false,
      isError: false,
      isSuccess: true,
    });
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("re-link")).toBeInTheDocument();
  });
});
