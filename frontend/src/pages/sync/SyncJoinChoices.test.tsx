// frontend/src/pages/sync/SyncJoinChoices.test.tsx
//
// The files a join left differing (6.5.19): each row names when each side
// edited it, a choice is staged per row, and "Apply N choices" sends the
// staged ones together — nothing is answered by a single click.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { ConflictFile } from "@/lib/api/sync";
import { SyncJoinChoices } from "./SyncJoinChoices";
import { idleMutation, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({ useJoinChoices: vi.fn(), useChooseJoin: vi.fn() }));
vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(() => Promise.resolve()) } }));

const hooks = await import("@/lib/hooks/useSyncStop");
const { useSyncStatus } = await import("@/lib/hooks/useSync");
const { fsApi } = await import("@/lib/api/fs");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const differing = (path: string): ConflictFile => ({
  path,
  area: "knowledge",
  reason: "join_differs",
  ours_time: "2026-09-26T09:00:00Z",
  theirs_time: "2026-09-27T09:00:00Z",
  theirs_machine: "Mac mini",
  other_path: null,
  answer: null,
  editor_path: null,
  secret: false,
  agent_merge: false,
});

let choose: ReturnType<typeof vi.fn>;
const seed = (files: ConflictFile[]) =>
  mocked(hooks.useJoinChoices).mockReturnValue({ data: { files } });

beforeEach(() => {
  choose = vi.fn();
  mocked(hooks.useChooseJoin).mockReturnValue(idleMutation({ mutate: choose }));
  mocked(useSyncStatus).mockReturnValue({ data: makeStatus() });
  seed([differing("knowledge/a.md"), differing("knowledge/b.md")]);
});
afterEach(() => vi.clearAllMocks());

const row = (path: string) => within(screen.getByTestId(`join-choice-${path}`));

describe("SyncJoinChoices", () => {
  test("each row says who edited it when", () => {
    render(<SyncJoinChoices />);
    expect(
      row("knowledge/a.md").getByText(/this Mac edited .* · Mac mini edited/),
    ).toBeInTheDocument();
    expect(screen.getByText("Differ from this Mac")).toBeInTheDocument();
  });

  test("choices are staged, then applied together", () => {
    render(<SyncJoinChoices />);
    const apply = () => screen.getByRole("button", { name: /^Apply \d+ choices?$/ });
    expect(apply()).toBeDisabled();

    fireEvent.click(row("knowledge/a.md").getByRole("button", { name: "Take Mac mini’s" }));
    fireEvent.click(row("knowledge/b.md").getByRole("button", { name: "Keep this Mac’s" }));
    expect(choose).not.toHaveBeenCalled();
    expect(row("knowledge/a.md").getByRole("button", { name: "Take Mac mini’s" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(apply());
    expect(choose).toHaveBeenCalledWith(
      [
        { path: "knowledge/a.md", answer: "theirs" },
        { path: "knowledge/b.md", answer: "mine" },
      ],
      expect.anything(),
    );
  });

  test("a file opens from the vault on this Mac", () => {
    render(<SyncJoinChoices />);
    fireEvent.click(row("knowledge/a.md").getByRole("button", { name: "Open knowledge/a.md" }));
    expect(fsApi.open).toHaveBeenCalledWith("/Users/me/.coffer/vault/knowledge/a.md");
  });

  test("a long list shows four and a way to the rest", () => {
    seed(["a", "b", "c", "d", "e", "f"].map((n) => differing(`knowledge/${n}.md`)));
    render(<SyncJoinChoices />);
    expect(screen.queryByTestId("join-choice-knowledge/e.md")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "…and 2 more" }));
    expect(screen.getByTestId("join-choice-knowledge/f.md")).toBeInTheDocument();
  });

  test("nothing differing renders nothing", () => {
    seed([]);
    const { container } = render(<SyncJoinChoices />);
    expect(container).toBeEmptyDOMElement();
  });
});
