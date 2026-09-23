// frontend/src/pages/sync/SyncRunDetail.test.tsx
//
// A path that can never apply on this machine is said to be not applicable
// here — its own list, not a failure the user has to chase (spec vault-sync
// "Record inapplicable paths as not applicable here").
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import type { RunRecord } from "@/lib/api/sync";
import { SyncRunDetail } from "./SyncRunDetail";

const NO_COUNTS = { added: 0, modified: 0, deleted: 0, changes: [] };

function run(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: 1,
    started_at: "2026-09-13T09:00:00Z",
    finished_at: "2026-09-13T09:00:04Z",
    status: "ok",
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: null,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    not_applicable: [],
    locked_refs: [],
    pending: null,
    join_report: null,
    error: null,
    ...overrides,
  };
}

describe("SyncRunDetail", () => {
  test("lists not-applicable paths apart from failures", () => {
    render(<SyncRunDetail run={run({ not_applicable: ["resources/agent/abc.yaml"] })} />);

    const list = screen.getByTestId("sync-run-not-applicable");
    expect(list).toHaveTextContent("resources/agent/abc.yaml");
    expect(list).toHaveTextContent(/not applicable on this machine/i);
    expect(screen.queryByTestId("sync-run-failures")).not.toBeInTheDocument();
    expect(screen.queryByText(/nothing further/i)).not.toBeInTheDocument();
  });

  test("a round waiting to join says how to join, and what it detected", () => {
    render(
      <SyncRunDetail
        run={run({
          status: "awaiting_join",
          join: "returning",
          join_report: {
            joining: true,
            case: "returning",
            base: "0123456789abcdef",
            last_converged_on: "2026-09-01",
            remote_changed: 7,
            vault_documents: 42,
          },
        })}
      />,
    );

    expect(screen.getByText(/has not joined this remote yet/i)).toBeInTheDocument();
    // Detected, not done: never "Rejoined as a returning machine".
    expect(screen.queryByText(/rejoined/i)).not.toBeInTheDocument();
    const report = screen.getByTestId("sync-join");
    expect(report).toHaveTextContent("2026-09-01");
    expect(report).toHaveTextContent(/changed since\s*7/i);
    expect(report).toHaveTextContent(/holds\s*42/i);
  });
});
