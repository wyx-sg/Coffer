// frontend/src/pages/sync/SyncStatusCard.test.tsx
//
// The status card says whether sync is working: the last round and what it
// moved, the next one, the machines, what the vault holds that syncs — and a
// problem, when there is one, in words that say what to do about it.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { SyncStatusCard } from "./SyncStatusCard";
import { idleMutation, makeRound, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useRunSync: vi.fn() }));
const { useRunSync } = await import("@/lib/hooks/useSync");
let run: ReturnType<typeof vi.fn>;

beforeEach(() => {
  run = vi.fn();
  (useRunSync as unknown as ReturnType<typeof vi.fn>).mockReturnValue(
    idleMutation({ mutate: run }),
  );
});
afterEach(() => vi.clearAllMocks());

describe("SyncStatusCard", () => {
  test("states the last round, the machines and the areas, and syncs now", () => {
    render(
      <SyncStatusCard
        status={makeStatus({
          machines: 3,
          last_round: makeRound({ pulled_files: 4, pushed_files: 2 }),
          areas: {
            knowledge_documents: 12,
            skills: 5,
            resources: 9,
            secrets: 2,
            secrets_synced: true,
          },
        })}
      />,
    );
    const facts = screen.getByTestId("sync-status-facts");
    expect(facts).toHaveTextContent(/4 pulled · 2 pushed/);
    expect(facts).toHaveTextContent("3");
    expect(facts).toHaveTextContent("12");
    expect(facts).toHaveTextContent(/2 synced/i);
    fireEvent.click(screen.getByRole("button", { name: /sync now/i }));
    expect(run).toHaveBeenCalled();
  });

  test("a refused sign-in names the credential reference and git's message", () => {
    render(
      <SyncStatusCard
        status={makeStatus({
          problem: {
            kind: "auth_failed",
            message: "remote: HTTP Basic: Access denied",
            secret_ref: "sync.PUSH_TOKEN",
            since: null,
          },
        })}
      />,
    );
    const banner = screen.getByTestId("sync-problem");
    expect(banner).toHaveTextContent("sync.PUSH_TOKEN");
    expect(banner).toHaveTextContent("Access denied");
  });

  test("a vault in a cloud-synced folder names the folder", () => {
    render(
      <SyncStatusCard
        status={makeStatus({
          synchroniser: "Dropbox",
          problem: { kind: "cloud_folder", message: "", secret_ref: null, since: null },
        })}
      />,
    );
    const banner = screen.getByTestId("sync-problem");
    expect(banner).toHaveTextContent("Dropbox");
    expect(banner).toHaveTextContent("/Users/me/.coffer/vault");
  });

  test("Sync now waits for a remote and a join", () => {
    render(<SyncStatusCard status={makeStatus({ joined: false })} />);
    expect(screen.getByRole("button", { name: /sync now/i })).toBeDisabled();
  });
});
