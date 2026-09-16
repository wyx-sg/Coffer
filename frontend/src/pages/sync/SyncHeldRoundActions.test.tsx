import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

vi.mock("@/lib/hooks/useSync", () => ({
  useConfirmRound: vi.fn(),
  useRejectRound: vi.fn(),
  useRebuildFromRemote: vi.fn(),
}));

import type { PendingConfirmation } from "@/lib/api/sync";
import { useConfirmRound, useRebuildFromRemote, useRejectRound } from "@/lib/hooks/useSync";
import { SyncHeldRoundActions } from "./SyncHeldRoundActions";

const confirmMock = useConfirmRound as unknown as ReturnType<typeof vi.fn>;
const rejectMock = useRejectRound as unknown as ReturnType<typeof vi.fn>;
const rebuildMock = useRebuildFromRemote as unknown as ReturnType<typeof vi.fn>;

function pending(over: Partial<PendingConfirmation> = {}): PendingConfirmation {
  return {
    direction: "publish",
    breaches: [{ area: "resources", deleted: 16, total: 45 }],
    paths: ["resources/memory/account.yaml", "resources/memory/global.yaml"],
    raised_at: "2026-09-17T00:12:14Z",
    ...over,
  };
}

const idle = () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() });

beforeEach(() => {
  vi.clearAllMocks();
  confirmMock.mockReturnValue(idle());
  rejectMock.mockReturnValue(idle());
  rebuildMock.mockReturnValue(idle());
});

describe("SyncHeldRoundActions", () => {
  test("confirming names what will happen before it happens", () => {
    // The row cannot carry sixteen paths, and this is a destructive answer in
    // either direction — so the dialog is where the round is described, not a
    // place that merely asks "are you sure?".
    render(<SyncHeldRoundActions pending={pending()} />);
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/16/);
    expect(dialog).toHaveTextContent(/45/);
    expect(dialog).toHaveTextContent("resources/memory/account.yaml");
    expect(dialog).toHaveTextContent("resources/memory/global.yaml");
  });

  test("the publish direction carries the reinstall warning; apply does not", () => {
    // Publishing a loss is how one damaged machine takes every other down with
    // it, and the honest answer there is Reject. That warning belongs only to
    // the direction it is true of.
    const publish = render(<SyncHeldRoundActions pending={pending({ direction: "publish" })} />);
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/reinstalled|restored from a backup/i);
    publish.unmount();

    render(<SyncHeldRoundActions pending={pending({ direction: "apply" })} />);
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(screen.getByRole("dialog")).not.toHaveTextContent(/reinstalled/i);
  });

  test("confirm runs only from inside the dialog", () => {
    const mutate = vi.fn();
    confirmMock.mockReturnValue({ ...idle(), mutate });
    render(<SyncHeldRoundActions pending={pending()} />);

    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(mutate).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^confirm$/i }));
    expect(mutate).toHaveBeenCalled();
  });

  test("a refused confirm keeps the dialog open with the reason", () => {
    confirmMock.mockReturnValue({ ...idle(), error: new Error("remote unreachable") });
    render(<SyncHeldRoundActions pending={pending()} />);
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^confirm$/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent(
      /remote unreachable/i,
    );
  });

  test("rejecting needs no confirmation — it is the answer that destroys nothing", () => {
    const mutate = vi.fn();
    rejectMock.mockReturnValue({ ...idle(), mutate });
    render(<SyncHeldRoundActions pending={pending()} />);

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("rebuild is offered on publish only, and asks first", () => {
    // Rebuilding discards what only this machine holds. It answers "my files
    // are really gone", which is a publish-direction question; on apply there
    // is nothing it could mean.
    const mutate = vi.fn();
    rebuildMock.mockReturnValue({ ...idle(), mutate });
    const publish = render(<SyncHeldRoundActions pending={pending({ direction: "publish" })} />);
    fireEvent.click(screen.getByRole("button", { name: /rebuild/i }));
    expect(mutate).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /rebuild/i }));
    expect(mutate).toHaveBeenCalled();
    publish.unmount();

    render(<SyncHeldRoundActions pending={pending({ direction: "apply" })} />);
    expect(screen.queryByRole("button", { name: /rebuild/i })).toBeNull();
  });

  test("a long path list is capped rather than scrolling past the confirm button", () => {
    const paths = Array.from({ length: 40 }, (_, i) => `resources/memory/p${i}.yaml`);
    render(<SyncHeldRoundActions pending={pending({ paths })} />);
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("resources/memory/p0.yaml");
    expect(dialog).not.toHaveTextContent("resources/memory/p39.yaml");
    expect(dialog).toHaveTextContent(/20/); // "…and 20 more"
  });
});
