// frontend/src/components/memory/MemoryDeliveryPanel.test.tsx
//
// Per-agent delivery state (spec memory FR-055 / ADR
// aggregate-agent-memory-never-write-it): "installed" is not the signal,
// "last fired" is — an installed hook that never actually ran must render as
// a warning, not a success, because that is exactly the failure mode the
// previous injection layer had for two months with nothing saying so.
import { describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { MemoryDeliveryPanel } from "./MemoryDeliveryPanel";
import type { DeliveryStatusOut } from "@/kinds/memory/types";

vi.mock("@/kinds/memory/useMemory", () => ({
  useMemoryDelivery: vi.fn(),
  useInstallDelivery: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveDelivery: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useMemoryDelivery } = await import("@/kinds/memory/useMemory");
const deliveryMock = vi.mocked(useMemoryDelivery);

function mockRows(rows: DeliveryStatusOut[]) {
  deliveryMock.mockReturnValue({
    data: rows,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useMemoryDelivery>);
}

describe("MemoryDeliveryPanel", () => {
  test("an installed-but-never-fired delivery renders as a warning", () => {
    mockRows([
      {
        agent: "codex",
        installed: true,
        command: "coffer memory context --agent codex",
        last_fired_at: "",
        event: "UserPromptSubmit",
      },
    ]);
    render(<MemoryDeliveryPanel />);

    const row = within(screen.getByTestId("memory-delivery-row-codex"));
    expect(screen.getByTestId("memory-delivery-warning-codex")).toBeInTheDocument();
    expect(row.getByText(/never fired/i)).toBeInTheDocument();
    // Not the plain success styling a fired install gets.
    expect(row.queryByText(/last fired/i)).toBeNull();
  });

  test("an installed delivery that has fired renders the last-fired time, not a warning", () => {
    mockRows([
      {
        agent: "claude_code",
        installed: true,
        command: "coffer memory context --agent claude_code",
        last_fired_at: "2026-09-12T10:00:00Z",
        event: "SessionStart",
      },
    ]);
    render(<MemoryDeliveryPanel />);

    const row = within(screen.getByTestId("memory-delivery-row-claude_code"));
    expect(screen.queryByTestId("memory-delivery-warning-claude_code")).toBeNull();
    expect(row.getByText(/last fired/i)).toBeInTheDocument();
  });

  test("a not-installed agent offers Install, not Remove", () => {
    mockRows([
      {
        agent: "codex",
        installed: false,
        command: "coffer memory context --agent codex",
        last_fired_at: "",
        event: "UserPromptSubmit",
      },
    ]);
    render(<MemoryDeliveryPanel />);

    expect(screen.getByRole("button", { name: /install/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).toBeNull();
  });
});
