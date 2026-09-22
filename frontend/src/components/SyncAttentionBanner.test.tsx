// src/components/SyncAttentionBanner.test.tsx — what the global banner says,
// and the far more important half: when it says nothing at all.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { ConvergeRound, SyncStatus } from "@/lib/api/sync";
import { SyncAttentionBanner } from "./SyncAttentionBanner";

vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));

const { useSyncStatus } = await import("@/lib/hooks/useSync");
const useSyncStatusMock = vi.mocked(useSyncStatus);

const NO_COUNTS = { added: 0, modified: 0, deleted: 0, changes: [] };

function round(status: ConvergeRound["status"]): ConvergeRound {
  return {
    status,
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: null,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    locked_refs: [],
    pending: null,
    error: null,
  };
}

const REMOTE = {
  url: "git@example.com:me/vault.git",
  branch: "main",
  credential_ref: "vault-push",
  interval_seconds: 900,
  enabled: true,
  worktree_path: "/Users/me/.coffer/sync",
} as SyncStatus["remote"];

function seed(overrides: Partial<SyncStatus> = {}, state: { isError?: boolean } = {}) {
  useSyncStatusMock.mockReturnValue({
    data: {
      configured: true,
      remote: REMOTE,
      last_run: null,
      machine_id: "m1",
      machine_id_is_derived: false,
      ...overrides,
    },
    isError: false,
    ...state,
  } as never);
}

function renderBanner(at = "/knowledge") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <SyncAttentionBanner />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SyncAttentionBanner", () => {
  // The four statuses the CLI also exits non-zero on: what needs a human must
  // reach the user on whatever page they are on, not only on /sync.
  test.each(["conflict", "awaiting_confirmation", "push_failed", "failed"] as const)(
    "carries a round that ended %s",
    (status) => {
      seed({ last_run: round(status) });
      renderBanner();
      expect(screen.getByTestId("sync-attention-banner")).toHaveAttribute(
        "data-round-status",
        status,
      );
      // Always a way to the page where the answer lives — the banner itself
      // deliberately offers no Confirm/Reject.
      expect(screen.getByRole("link", { name: /sync/i })).toHaveAttribute("href", "/sync");
      expect(screen.queryByRole("button")).toBeNull();
    },
  );

  test("a held round reads differently from a failed one — nothing converges until it is answered", () => {
    seed({ last_run: round("awaiting_confirmation") });
    const { unmount } = renderBanner();
    const heldTitle = screen.getByTestId("sync-attention-banner").textContent ?? "";
    expect(heldTitle).toMatch(/waiting for your answer/i);
    unmount();

    seed({ last_run: round("failed") });
    renderBanner();
    const failedTitle = screen.getByTestId("sync-attention-banner").textContent ?? "";
    expect(failedTitle).not.toMatch(/waiting for your answer/i);
    expect(failedTitle).not.toEqual(heldTitle);
  });

  test.each(["ok", "no_change", "disabled"] as const)("stays silent after a %s round", (status) => {
    seed({ last_run: round(status) });
    const { container } = renderBanner();
    expect(container.firstChild).toBeNull();
  });

  test("stays silent when no remote is configured", () => {
    // Do not nag a user who never enabled sync — there is nothing to converge
    // and nothing for them to answer.
    seed({ configured: false, remote: null, last_run: round("failed") });
    const { container } = renderBanner();
    expect(container.firstChild).toBeNull();
  });

  test("stays silent when no round has run yet", () => {
    seed({ last_run: null });
    const { container } = renderBanner();
    expect(container.firstChild).toBeNull();
  });

  test("stands down while sync is switched off", () => {
    // Load-bearing. A disabled remote makes the daemon return a `disabled`
    // round WITHOUT recording it, so `last_run` keeps whatever it last was —
    // and a user who meets a hold by switching sync off rather than answering
    // it would otherwise be told about that hold on every page for ever.
    seed({
      remote: { ...REMOTE, enabled: false } as SyncStatus["remote"],
      last_run: round("awaiting_confirmation"),
    });
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  test("brings its own card and not its own fixed slot", () => {
    // The slot is `FloatingBanners`, and it is shared. When this component
    // owned an identical `fixed inset-x-0 top-4` wrapper of its own, it and
    // DaemonOfflineBanner were drawn at the same coordinates and whichever
    // painted second hid the other outright.
    seed({ last_run: round("conflict") });
    const { container } = renderBanner();
    expect(container.querySelector(".fixed")).toBeNull();
    expect(screen.getByTestId("sync-attention-banner")).toBeInTheDocument();
  });

  test("stands down on the sync page itself, where the answer already is", () => {
    // Not a cosmetic call. The banner floats over the page, and on `/sync` it
    // would sit across the very row that carries the diff and the Confirm /
    // Reject the hold is waiting for (spec vault-sync FR-096).
    seed({ last_run: round("awaiting_confirmation") });
    const { container } = renderBanner("/sync");
    expect(container).toBeEmptyDOMElement();
  });

  test("stays silent while the status query is failing", () => {
    // An unreachable daemon has its own banner in the same fixed position and
    // the same recovery; stale cached data must not stack a second one on it.
    seed({ last_run: round("awaiting_confirmation") }, { isError: true });
    const { container } = renderBanner();
    expect(container.firstChild).toBeNull();
  });
});
