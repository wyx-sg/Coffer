// frontend/src/pages/sync/SyncHoldCard.test.tsx
//
// A held round has two answers, each naming how many files it touches:
// Delete (asked again, because it destroys) and Restore (at once). The files
// are grouped by folder with each folder's share, so 12 of 400 and 12 of 12
// never read as the same thing.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { SyncHold } from "@/lib/api/sync";
import { SyncHoldCard } from "./SyncHoldCard";
import { idleMutation } from "./syncTestKit";

vi.mock("@/lib/hooks/useSyncStop", () => ({
  useConfirmHold: vi.fn(),
  useRestoreHold: vi.fn(),
}));

const hooks = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const PATHS = ["knowledge/team/a.md", "knowledge/team/b.md", "knowledge/team/c.md"];

function hold(over: Partial<SyncHold> = {}): SyncHold {
  return {
    direction: "incoming",
    breaches: [{ area: "knowledge", lost: 3, total: 4 }],
    paths: PATHS,
    groups: [{ folder: "knowledge/team", paths: PATHS, total: 4 }],
    machines: ["Mac mini"],
    confirmed: false,
    ...over,
  };
}

let confirm: ReturnType<typeof vi.fn>;
let restore: ReturnType<typeof vi.fn>;

beforeEach(() => {
  confirm = vi.fn((_: undefined, opts: { onSuccess: () => void }) => opts.onSuccess());
  restore = vi.fn();
  mocked(hooks.useConfirmHold).mockReturnValue(idleMutation({ mutate: confirm }));
  mocked(hooks.useRestoreHold).mockReturnValue(idleMutation({ mutate: restore }));
});
afterEach(() => vi.clearAllMocks());

describe("SyncHoldCard", () => {
  test("says who deleted how many, grouped by folder with its share", () => {
    render(<SyncHoldCard hold={hold()} />);
    const card = screen.getByTestId("sync-hold");
    expect(card).toHaveTextContent(/Mac mini deleted 3 files/);
    expect(card).toHaveTextContent("knowledge/team");
    expect(card).toHaveTextContent(/3 files · 75% of the folder/);
    for (const path of PATHS) expect(card).toHaveTextContent(path);
  });

  test("an outgoing hold names this Mac", () => {
    render(<SyncHoldCard hold={hold({ direction: "outgoing", machines: [] })} />);
    expect(screen.getByTestId("sync-hold")).toHaveTextContent(/This Mac deleted 3 files/);
  });

  test("Delete asks first, then confirms the hold", () => {
    render(<SyncHoldCard hold={hold()} />);
    fireEvent.click(screen.getByRole("button", { name: /delete 3 files/i }));
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: /delete 3 files/i }),
    );
    expect(confirm).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("Restore keeps the files at once — it destroys nothing", () => {
    render(<SyncHoldCard hold={hold()} />);
    fireEvent.click(screen.getByRole("button", { name: /restore 3 files/i }));
    expect(restore).toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
