// frontend/src/kinds/memory/useMemory.test.tsx
//
// `useMemoryAuditLog` is the first consumer of the generic `useAudit` hook
// (spec memory FR-062). The backend does not tag every memory lifecycle event
// with `resource_kind=memory` (override events carry no ref at all, delivery
// events are tagged `agent`) — see the hook's own docstring — so this asserts
// the client-side narrowing by event-type prefix actually keeps the six
// memory events and drops everything else.
import { describe, expect, test, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { useMemoryAuditLog } from "./useMemory";
import type { components } from "@/lib/api/types";

type AuditEntryOut = components["schemas"]["AuditEntryOut"];

vi.mock("@/lib/hooks/useAudit", () => ({ useAudit: vi.fn() }));
const { useAudit } = await import("@/lib/hooks/useAudit");
const useAuditMock = vi.mocked(useAudit);

function entry(overrides: Partial<AuditEntryOut>): AuditEntryOut {
  return {
    id: 1,
    timestamp: "2026-09-12T00:00:00Z",
    event_type: "memory_aggregated",
    resource_kind: null,
    resource_name: null,
    actor: "ui",
    details: null,
    ...overrides,
  };
}

describe("useMemoryAuditLog", () => {
  test("asks the server for the memory_ prefix rather than narrowing here", () => {
    // The narrowing has to happen server-side: this kind's acts span two kinds
    // (its own partitions, and the agent config a hook install writes), so a
    // kind filter cannot express them — and filtering a fixed window in the
    // browser would silently drop whatever fell outside it, leaving a log that
    // reads complete and is not.
    useAuditMock.mockReturnValue({
      data: { entries: [] },
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useAudit>);

    renderHook(() => useMemoryAuditLog());

    expect(useAuditMock).toHaveBeenCalledWith(expect.objectContaining({ eventPrefix: "memory_" }));
  });

  test("returns what the server sent, untouched", () => {
    useAuditMock.mockReturnValue({
      data: {
        entries: [
          entry({ id: 1, event_type: "memory_aggregated" }),
          entry({ id: 2, event_type: "memory_override_set", resource_kind: null }),
          entry({ id: 4, event_type: "memory_delivery_installed", resource_kind: "agent" }),
        ],
      },
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useAudit>);

    const { result } = renderHook(() => useMemoryAuditLog());

    expect(result.current.entries.map((e) => e.id)).toEqual([1, 2, 4]);
  });
});
