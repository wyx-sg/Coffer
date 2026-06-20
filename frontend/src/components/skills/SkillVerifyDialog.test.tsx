// frontend/src/components/skills/SkillVerifyDialog.test.tsx
//
// The drift dialog must not flash a false "no drift detected" before the verify
// mutation actually runs (FE5): while the mutation is idle/pending (entries is
// an empty array but isSuccess is false), it shows the checking spinner — the OK
// branch is gated on verify.isSuccess.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { SkillVerifyDialog } from "./SkillVerifyDialog";

vi.mock("@/lib/hooks/useSkills", () => ({
  useVerifySkills: vi.fn(),
  useRepairSkillDrift: vi.fn(),
}));
const { useVerifySkills, useRepairSkillDrift } = await import("@/lib/hooks/useSkills");
const useVerifySkillsMock = vi.mocked(useVerifySkills);
const useRepairSkillDriftMock = vi.mocked(useRepairSkillDrift);

function stubVerify(state: Record<string, unknown>) {
  useVerifySkillsMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    ...state,
  } as unknown as ReturnType<typeof useVerifySkills>);
}

function stubRepair(state: Record<string, unknown>) {
  useRepairSkillDriftMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    ...state,
  } as unknown as ReturnType<typeof useRepairSkillDrift>);
}

afterEach(() => vi.clearAllMocks());

describe("SkillVerifyDialog", () => {
  test("does not show the OK state while the mutation is still idle/pending", () => {
    // Idle: empty entries but NOT yet successful — must show the spinner, never OK.
    stubVerify({ data: { entries: [] }, isPending: false, isError: false, isSuccess: false });
    stubRepair({});
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);

    expect(screen.getByText(/checking/i)).toBeInTheDocument();
    expect(screen.queryByText(/no drift/i)).not.toBeInTheDocument();
  });

  test("shows the OK state only once the verify mutation succeeds with no entries", () => {
    stubVerify({ data: { entries: [] }, isPending: false, isError: false, isSuccess: true });
    stubRepair({});
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);

    expect(screen.getByText(/no drift/i)).toBeInTheDocument();
    expect(screen.queryByText(/checking/i)).not.toBeInTheDocument();
  });

  test("lists drift entries once succeeded", () => {
    stubVerify({
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
    stubRepair({});
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("re-link")).toBeInTheDocument();
  });

  test("shows a Repair button when drift is present", () => {
    stubVerify({
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
    stubRepair({});
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);
    expect(screen.getByRole("button", { name: /repair/i })).toBeInTheDocument();
  });

  test("does not show Repair button when there is no drift", () => {
    stubVerify({ data: { entries: [] }, isPending: false, isError: false, isSuccess: true });
    stubRepair({});
    render(<SkillVerifyDialog open onOpenChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /repair/i })).not.toBeInTheDocument();
  });

  test("clicking Repair calls repair endpoint and renders remediated + remaining sections", () => {
    // The repair mutate will call its onSuccess callback with the result.
    const repairMutate = vi.fn((_vars: unknown, opts?: { onSuccess?: (data: unknown) => void }) => {
      opts?.onSuccess?.({
        remediated: [
          {
            skill_name: "hello",
            agent_name: "cc",
            kind: "missing_link",
            target_path: "/x",
            suggested_remedy: "re-link",
          },
        ],
        remaining: {
          entries: [
            {
              skill_name: "other",
              agent_name: "cc",
              kind: "foreign_content",
              target_path: "/y",
              suggested_remedy: "manual action required",
            },
          ],
        },
      });
    });

    stubVerify({
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
    stubRepair({ mutate: repairMutate });

    render(<SkillVerifyDialog open onOpenChange={() => {}} />);

    const repairBtn = screen.getByRole("button", { name: /repair/i });
    fireEvent.click(repairBtn);

    // The repair mutate should have been called.
    expect(repairMutate).toHaveBeenCalledOnce();

    // The repaired section should be visible.
    expect(screen.getByText(/repaired/i)).toBeInTheDocument();
    // The remaining section should be visible.
    expect(screen.getByText(/still needs manual action/i)).toBeInTheDocument();
    // Remediated entry skill name visible.
    expect(screen.getByText("hello")).toBeInTheDocument();
    // Remaining entry skill name visible.
    expect(screen.getByText("other")).toBeInTheDocument();
    // The Repair button should be gone after repair result is shown.
    expect(screen.queryByRole("button", { name: /repair/i })).not.toBeInTheDocument();
  });

  test("repair result is NOT filtered by skillNames — shows entries from other skills too", () => {
    // Dialog opened scoped to "hello" only (per-row verify), but the repair
    // endpoint returns a result that also covers "other-skill". The post-repair
    // view must show "other-skill" unfiltered, plus the global note.
    const repairMutate = vi.fn((_vars: unknown, opts?: { onSuccess?: (data: unknown) => void }) => {
      opts?.onSuccess?.({
        remediated: [
          {
            skill_name: "hello",
            agent_name: "cc",
            kind: "missing_link",
            target_path: "/x",
            suggested_remedy: "re-link",
          },
          {
            skill_name: "other-skill",
            agent_name: "codex",
            kind: "missing_link",
            target_path: "/z",
            suggested_remedy: "re-link other",
          },
        ],
        remaining: {
          entries: [
            {
              skill_name: "yet-another-skill",
              agent_name: "cc",
              kind: "foreign_content",
              target_path: "/w",
              suggested_remedy: "manual fix needed",
            },
          ],
        },
      });
    });

    // Verify is scoped to "hello" only (as from per-row action in SkillsTable).
    stubVerify({
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
    stubRepair({ mutate: repairMutate });

    // Open dialog scoped to "hello" only.
    render(<SkillVerifyDialog open onOpenChange={() => {}} skillNames={["hello"]} />);

    const repairBtn = screen.getByRole("button", { name: /repair/i });
    fireEvent.click(repairBtn);

    // The global note must be visible to inform the user that repair is system-wide.
    expect(
      screen.getByText(/repair re-delivers every drifted skill from master/i),
    ).toBeInTheDocument();

    // "other-skill" is NOT in skillNames but must appear in the repair result (unfiltered).
    expect(screen.getByText("other-skill")).toBeInTheDocument();
    // "yet-another-skill" is NOT in skillNames but must appear in remaining (unfiltered).
    expect(screen.getByText("yet-another-skill")).toBeInTheDocument();
  });
});
