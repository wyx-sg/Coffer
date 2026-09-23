// frontend/src/pages/sync/SyncConvergeAction.test.tsx
//
// "Converge now" on a machine that has not joined yet: the join is stated —
// its case, when this machine last converged, what the remote changed since,
// what this vault holds — before anything is applied, and it happens only
// from the dialog (spec vault-sync "Report a join before applying it").
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

vi.mock("@/lib/hooks/useSync", () => ({
  useRunConverge: vi.fn(),
  usePreviewJoin: vi.fn(),
  useAdoptRemote: vi.fn(),
}));

import type { JoinPreview } from "@/lib/api/sync";
import { useAdoptRemote, usePreviewJoin, useRunConverge } from "@/lib/hooks/useSync";
import { SyncConvergeAction } from "./SyncConvergeAction";

const runMock = useRunConverge as unknown as ReturnType<typeof vi.fn>;
const previewMock = usePreviewJoin as unknown as ReturnType<typeof vi.fn>;
const adoptMock = useAdoptRemote as unknown as ReturnType<typeof vi.fn>;

const idle = () => ({ mutate: vi.fn(), isPending: false, error: null, reset: vi.fn() });

function answering(preview: JoinPreview) {
  return {
    ...idle(),
    mutate: vi.fn((_: undefined, opts: { onSuccess: (p: JoinPreview) => void }) =>
      opts.onSuccess(preview),
    ),
  };
}

const returning: JoinPreview = {
  joining: true,
  case: "returning",
  base: null,
  last_converged_on: "2026-09-01",
  remote_changed: 7,
  vault_documents: 42,
};

beforeEach(() => {
  vi.clearAllMocks();
  runMock.mockReturnValue(idle());
  adoptMock.mockReturnValue(idle());
});

const convergeNow = () => fireEvent.click(screen.getByRole("button", { name: /converge now/i }));

describe("SyncConvergeAction", () => {
  test("a machine already converged here runs its round without a dialog", () => {
    const run = idle();
    runMock.mockReturnValue(run);
    previewMock.mockReturnValue(
      answering({
        joining: false,
        case: null,
        base: null,
        last_converged_on: null,
        remote_changed: null,
        vault_documents: null,
      }),
    );
    render(<SyncConvergeAction disabled={false} />);

    convergeNow();

    expect(run.mutate).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("a join states its case and counts, and applies nothing until confirmed", () => {
    const run = idle();
    const adopt = idle();
    runMock.mockReturnValue(run);
    adoptMock.mockReturnValue(adopt);
    previewMock.mockReturnValue(answering(returning));
    render(<SyncConvergeAction disabled={false} />);

    convergeNow();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/synced here before/i);
    expect(dialog).toHaveTextContent("2026-09-01");
    expect(within(dialog).getByTestId("sync-join")).toHaveTextContent(/changed since\s*7/i);
    expect(within(dialog).getByTestId("sync-join")).toHaveTextContent(/holds\s*42/i);
    expect(run.mutate).not.toHaveBeenCalled();
    expect(adopt.mutate).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: /^join$/i }));
    expect(adopt.mutate).toHaveBeenCalledWith(undefined, expect.anything());
  });

  test("a new machine says it takes the union and has never converged", () => {
    previewMock.mockReturnValue(
      answering({
        joining: true,
        case: "new",
        base: null,
        last_converged_on: null,
        remote_changed: 3,
        vault_documents: 1,
      }),
    );
    render(<SyncConvergeAction disabled={false} />);

    convergeNow();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/takes the union/i);
    expect(dialog).toHaveTextContent(/never/i);
  });

  test("an ambiguous join joins only on the explicit keep-local answer", () => {
    const adopt = idle();
    adoptMock.mockReturnValue(adopt);
    previewMock.mockReturnValue(
      answering({
        joining: true,
        case: "ambiguous",
        base: null,
        last_converged_on: "2026-09-01",
        remote_changed: null,
        vault_documents: 4,
      }),
    );
    render(<SyncConvergeAction disabled={false} />);

    convergeNow();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/cannot be recovered/i);
    expect(dialog).not.toHaveTextContent(/changed since/i);
    fireEvent.click(within(dialog).getByRole("button", { name: /keep this vault's documents/i }));
    expect(adopt.mutate).toHaveBeenCalledWith("keep-local", expect.anything());
  });

  test("a refused join keeps the dialog open with the reason", () => {
    adoptMock.mockReturnValue({ ...idle(), error: new Error("remote unreachable") });
    previewMock.mockReturnValue(answering(returning));
    render(<SyncConvergeAction disabled={false} />);

    convergeNow();

    expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent(
      /remote unreachable/i,
    );
  });
});
