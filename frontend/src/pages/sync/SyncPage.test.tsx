// frontend/src/pages/sync/SyncPage.test.tsx
//
// Sync is a top-level page with three tabs — Status, Machines and Remote —
// and it opens on Status, because what a person opens Sync to find out is
// whether this Mac is in sync. The header says it in one pill beside the
// title, with the remote under it and the one action on the right. A Mac with
// no remote, or one not joined yet, has no tabs: it is set up first.
//
// The active tab is in the URL, so a link can land on Remote and a reload
// comes back where it was; the retired Runs and Setup tabs land on Status.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import type { SyncStatus } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";
import { SyncPage } from "./SyncPage";
import { idleMutation, makeRound, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn(), useRunSync: vi.fn() }));
vi.mock("./SyncStatusTab", () => ({ SyncStatusTab: () => <div>status tab</div> }));
vi.mock("./SyncMachinesTab", () => ({ SyncMachinesTab: () => <div>machines tab</div> }));
vi.mock("./SyncRemoteTab", () => ({ SyncRemoteTab: () => <div>remote tab</div> }));
vi.mock("./SyncSetup", () => ({ SyncSetup: () => <div>setup flow</div> }));

const { useSyncStatus, useRunSync } = await import("@/lib/hooks/useSync");

let search = "";
function Probe() {
  search = useLocation().search;
  return null;
}

function seed(status: SyncStatus | undefined, run = idleMutation()) {
  vi.mocked(useSyncStatus).mockReturnValue({
    data: status,
    isPending: status === undefined,
    error: null,
  } as unknown as ReturnType<typeof useSyncStatus>);
  vi.mocked(useRunSync).mockReturnValue(run as unknown as ReturnType<typeof useRunSync>);
  return run;
}

function renderAt(url = "/sync") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <SyncPage />
      <Probe />
    </MemoryRouter>,
  );
}

const pill = () => screen.getByTestId("sync-pill");

beforeEach(() => void seed(makeStatus()));
afterEach(() => vi.clearAllMocks());

describe("SyncPage — tabs", () => {
  acceptance("vault-sync", "the Sync page opens on Status beside Machines and Remote", () => {
    const view = renderAt();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Status", "Machines", "Remote"]);
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("status tab")).toBeInTheDocument();
    view.unmount();

    // A link to a retired tab lands on Status rather than nowhere.
    for (const stale of ["runs", "setup", "nope"]) {
      const again = renderAt(`/sync?tab=${stale}`);
      expect(screen.getAllByRole("tab")).toHaveLength(3);
      expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByText("status tab")).toBeInTheDocument();
      again.unmount();
    }
  });

  test("?tab= opens that tab, and switching tabs rewrites the URL", async () => {
    renderAt("/sync?tab=remote");
    expect(screen.getByRole("tab", { name: "Remote" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("remote tab")).toBeInTheDocument();

    // Radix activates a trigger on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Status" }));
    // The landing tab needs no parameter, so the page's own URL is the shortest.
    await waitFor(() => expect(search).toBe(""));
    expect(screen.getByText("status tab")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Machines" }));
    await waitFor(() => expect(search).toBe("?tab=machines"));
    expect(screen.getByText("machines tab")).toBeInTheDocument();
  });

  test("a Mac with no remote, or not joined yet, has no tabs and shows the setup flow", () => {
    for (const status of [
      makeStatus({ configured: false, remote: null, joined: false }),
      makeStatus({ joined: false }),
    ]) {
      seed(status);
      const view = renderAt();
      expect(screen.queryAllByRole("tab")).toHaveLength(0);
      expect(screen.getByText("setup flow")).toBeInTheDocument();
      expect(pill()).toHaveTextContent("Not set up");
      expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
      view.unmount();
    }
  });
});

describe("SyncPage — header", () => {
  test("title, the add-a-Mac help, the pill, and the remote with a copy button", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    seed(
      makeStatus({
        remote: {
          ...makeStatus().remote!,
          url: "git@github.com:me/vault.git",
          interval_seconds: 3600,
        },
      }),
    );
    renderAt();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sync");
    expect(screen.getByRole("button", { name: "How to add another Mac" })).toBeInTheDocument();
    expect(pill()).toHaveTextContent("In sync");
    expect(screen.getByText("git@github.com:me/vault.git")).toBeInTheDocument();
    expect(screen.getByText(/· main · every hour/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy repository URL" }));
    });
    expect(writeText).toHaveBeenCalledWith("git@github.com:me/vault.git");
  });

  test("Sync now runs a round; while it runs the button reads Syncing… and the pill Syncing", () => {
    const run = seed(makeStatus());
    const view = renderAt();
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    expect(run.mutate).toHaveBeenCalled();
    view.unmount();

    seed(makeStatus({ running_since: "2026-09-29T14:32:00Z" }));
    renderAt();
    expect(pill()).toHaveTextContent("Syncing");
    expect(screen.getByRole("button", { name: /Syncing…/ })).toBeDisabled();
  });

  test.each([
    ["unreachable", "Remote unreachable", "Try again"],
    ["auth_failed", "Sign-in failed", "Try again"],
    ["push_failed", "Push failed", "Sync now"],
    ["cloud_folder", "Paused", "Sync now"],
    ["git_missing", "Git missing", "Sync now"],
  ] as const)("a %s problem reads %s, with %s", (kind, word, action) => {
    seed(
      makeStatus({
        problem: { kind, message: "", secret_ref: null, since: null, handoff: null, plaintext: [] },
      }),
    );
    renderAt();
    expect(pill()).toHaveTextContent(word);
    expect(screen.getByRole("button", { name: action })).toBeEnabled();
  });

  test("a stopped round counts what it stopped on, and Sync now waits for the answer", () => {
    seed(makeStatus({ conflicts: 2 }));
    const view = renderAt();
    expect(pill()).toHaveTextContent("Stopped: 2 conflicts");
    expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled();
    view.unmount();

    seed(makeStatus({ held: 14 }));
    renderAt();
    expect(pill()).toHaveTextContent("Stopped: 14 deletions held");
  });

  test("changes to push and changes pulled are counted in the pill", () => {
    seed(
      makeStatus({
        waiting: [
          {
            version: "v",
            time: "2026-09-29T14:28:00Z",
            writer: "user",
            summary: "",
            changes: [
              { path: "a.md", status: "modified" },
              { path: "b.md", status: "added" },
            ],
          },
        ],
      }),
    );
    const view = renderAt();
    expect(pill()).toHaveTextContent("2 changes to push");
    view.unmount();

    seed(makeStatus({ last_round: makeRound({ status: "pulled", pulled_files: 3 }) }));
    renderAt();
    expect(within(pill()).getByText("3 changes pulled")).toBeInTheDocument();
  });

  test("a paused remote reads Paused", () => {
    const status = makeStatus();
    seed({ ...status, remote: { ...status.remote!, enabled: false } });
    renderAt();
    expect(pill()).toHaveTextContent("Paused");
  });
});
