// frontend/src/pages/sync/SyncSetup.test.tsx
//
// First run (6.5.16 → 6.5.17 / 6.5.18): nothing is stored until Check
// repository has looked at the draft. An empty repository says what the
// first round pushes and, on Push and start syncing, stores the remote and
// joins; a vault stores the remote so the join preview follows; anything
// else is said under the form. A stored-but-unjoined remote opens on the
// preview, whose Back forgets it.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { RemoteCheck, SyncStatus } from "@/lib/api/sync";
import { SyncSetup } from "./SyncSetup";
import { idleMutation, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({
  useCheckRemote: vi.fn(),
  useSaveSyncRemote: vi.fn(),
  useClearSyncRemote: vi.fn(),
}));
vi.mock("@/lib/hooks/useSyncStop", () => ({ useJoin: vi.fn(), useJoinPreview: vi.fn() }));
vi.mock("@/lib/hooks/useSecrets", () => ({ useSecrets: vi.fn(() => ({ data: { refs: [] } })) }));

const sync = await import("@/lib/hooks/useSync");
const stop = await import("@/lib/hooks/useSyncStop");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

let check: ReturnType<typeof vi.fn>;
let save: ReturnType<typeof vi.fn>;
let clear: ReturnType<typeof vi.fn>;
let join: ReturnType<typeof vi.fn>;

/** `check.mutate` answers at once with `result`, as the daemon would. */
function answer(result: RemoteCheck["result"], detail: string | null = null) {
  check.mockImplementation((_body, opts) => {
    const data = { result, detail, layout: null, tip: null };
    mocked(sync.useCheckRemote).mockReturnValue(idleMutation({ mutate: check, data }));
    opts?.onSuccess?.(data);
  });
}

beforeEach(() => {
  check = vi.fn();
  save = vi.fn((_body, opts) => opts?.onSuccess?.());
  clear = vi.fn();
  join = vi.fn();
  mocked(sync.useCheckRemote).mockReturnValue(idleMutation({ mutate: check, data: undefined }));
  mocked(sync.useSaveSyncRemote).mockReturnValue(idleMutation({ mutate: save }));
  mocked(sync.useClearSyncRemote).mockReturnValue(idleMutation({ mutate: clear }));
  mocked(stop.useJoin).mockReturnValue(idleMutation({ mutate: join }));
  mocked(stop.useJoinPreview).mockReturnValue({ data: undefined, isLoading: true, error: null });
});
afterEach(() => vi.clearAllMocks());

const notSetUp = (): SyncStatus => ({
  ...makeStatus({ configured: false, joined: false, remote: null }),
  areas: { knowledge_documents: 142, skills: 38, resources: 24, secrets: 8, secrets_synced: false },
});

function fillAndCheck(url: string) {
  fireEvent.change(screen.getByLabelText("Repository URL"), { target: { value: url } });
  fireEvent.click(screen.getByRole("button", { name: "Check repository" }));
}

describe("SyncSetup", () => {
  test("opens on the defaults, and Check repository waits for a URL", () => {
    render(<SyncSetup status={notSetUp()} />);
    expect(screen.getByText("Keep this vault in a git repository you own")).toBeInTheDocument();
    expect(screen.getByLabelText("Branch")).toHaveValue("main");
    expect(screen.getByRole("combobox", { name: "Run a round" })).toHaveTextContent("Every hour");
    expect(screen.getByRole("button", { name: "Check repository" })).toBeDisabled();
  });

  test("the check is asked of the draft, with the user name for an HTTPS URL", () => {
    render(<SyncSetup status={notSetUp()} />);
    fireEvent.change(screen.getByLabelText("Repository URL"), {
      target: { value: "https://gitlab.com/me/vault.git" },
    });
    fireEvent.change(screen.getByLabelText("User name"), { target: { value: "oauth2" } });
    fireEvent.click(screen.getByRole("button", { name: "Check repository" }));
    expect(check).toHaveBeenCalledWith(
      {
        url: "https://gitlab.com/me/vault.git",
        branch: "main",
        secret_ref: null,
        username: "oauth2",
      },
      expect.anything(),
    );
    expect(save).not.toHaveBeenCalled();
  });

  test("an empty repository says what is pushed, then stores the remote and joins", () => {
    answer("empty");
    render(<SyncSetup status={notSetUp()} />);
    fillAndCheck("git@github.com:me/vault.git");
    const panel = screen.getByTestId("sync-setup-empty");
    expect(panel).toHaveTextContent("The repository is empty");
    expect(panel).toHaveTextContent("142 files");
    expect(panel).toHaveTextContent("38 skills");
    expect(panel).toHaveTextContent("24 definitions");
    expect(panel).toHaveTextContent(/secrets are not included/i);
    expect(save).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Push and start syncing" }));
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ url: "git@github.com:me/vault.git", enabled: true }),
      expect.anything(),
    );
    expect(join).toHaveBeenCalled();
  });

  test("Back from the empty repository returns to the form with the draft kept", () => {
    answer("empty");
    render(<SyncSetup status={notSetUp()} />);
    fillAndCheck("git@github.com:me/vault.git");
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("Repository URL")).toHaveValue("git@github.com:me/vault.git");
  });

  test("a repository that holds a vault is stored, so the join preview follows", () => {
    answer("vault");
    render(<SyncSetup status={notSetUp()} />);
    fillAndCheck("git@github.com:me/vault.git");
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ url: "git@github.com:me/vault.git" }),
    );
    expect(join).not.toHaveBeenCalled();
  });

  test.each([
    ["other", /not a Coffer vault/],
    ["unreachable", /can’t be reached/],
    ["auth_failed", /sign-in was refused/i],
  ] as const)("a %s repository is said under the form, with git's words", (result, text) => {
    answer(result, "fatal: nope");
    render(<SyncSetup status={notSetUp()} />);
    fillAndCheck("git@github.com:me/vault.git");
    const said = screen.getByTestId("sync-remote-check");
    expect(said).toHaveTextContent(text);
    expect(said).toHaveTextContent("fatal: nope");
    expect(save).not.toHaveBeenCalled();
  });

  test("a stored remote not yet joined opens on the preview; Back forgets it", () => {
    render(<SyncSetup status={makeStatus({ joined: false })} />);
    expect(screen.getByTestId("sync-join")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(clear).toHaveBeenCalled();
  });
});
