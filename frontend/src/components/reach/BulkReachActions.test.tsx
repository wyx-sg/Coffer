// frontend/src/components/reach/BulkReachActions.test.tsx
//
// The bulk half of the reach control: each segment writes the SAME state to
// EVERY selected row, and partial failure is reported rather than swallowed.
// The old bar offered Enable/Disable only, which could not express the state the
// rows themselves could be in.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { BulkReachActions } from "./BulkReachActions";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "claude" }, { name: "codex" }] })),
}));
vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: vi.fn(() => ({
    data: { machines: [{ machine_id: "a3f21c9e4b7d2610", name: "laptop", is_self: true }] },
  })),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: { success: toastSuccess, error: toastError } }),
  ToastProvider: ({ children }: PropsWithChildren) => children,
}));

const { resourcesApi } = await import("@/lib/api/resources");
const { scopeApi } = await import("@/lib/api/scope");
const resources = resourcesApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const scope = scopeApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const ROWS = [
  { kind: "skill", name: "writing" },
  { kind: "skill", name: "reviewing" },
];

function mount(props: Partial<Parameters<typeof BulkReachActions>[0]> = {}) {
  const onDone = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <BulkReachActions rows={ROWS} onDone={onDone} {...props} />
    </QueryClientProvider>,
  );
  return { onDone, qc };
}

const bar = () => within(screen.getByTestId("bulk-reach-control"));

afterEach(() => vi.clearAllMocks());

describe("BulkReachActions", () => {
  test("Disabled disables every selected row and writes no scope", async () => {
    resources.disable.mockResolvedValue(undefined);
    const { onDone } = mount();

    fireEvent.click(bar().getByRole("button", { name: /^disabled$/i }));

    await waitFor(() => expect(resources.disable).toHaveBeenCalledTimes(2));
    expect(resources.disable.mock.calls.map((c) => c[1]).sort()).toEqual(["reviewing", "writing"]);
    expect(scope.put).not.toHaveBeenCalled();
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  test("Everywhere enables each row and clears its scope", async () => {
    resources.enable.mockResolvedValue(undefined);
    scope.put.mockResolvedValue(undefined);
    mount();

    fireEvent.click(bar().getByRole("button", { name: /everywhere/i }));

    await waitFor(() => expect(scope.put).toHaveBeenCalledTimes(2));
    expect(resources.enable).toHaveBeenCalledTimes(2);
    expect(scope.put.mock.calls.every((c) => c[2] === null)).toBe(true);
  });

  test("Restricted writes the SAME staged scope to every row, once", async () => {
    resources.enable.mockResolvedValue(undefined);
    scope.put.mockResolvedValue(undefined);
    mount();

    fireEvent.click(bar().getByRole("button", { name: /restricted/i }));
    // The panel opens on an EMPTY draft: a bulk write is a new intent, not an
    // edit of whichever row happened to be first.
    expect(
      within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"),
    ).not.toBeChecked();

    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    expect(scope.put).not.toHaveBeenCalled();

    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await waitFor(() => expect(scope.put).toHaveBeenCalledTimes(2));
    expect(scope.put.mock.calls.map((c) => [c[1], c[2]])).toEqual([
      ["writing", { agents: ["claude"], machines: null }],
      ["reviewing", { agents: ["claude"], machines: null }],
    ]);
  });

  test("a kind with no scope gets two segments, and Enabled writes only the flag", async () => {
    resources.enable.mockResolvedValue(undefined);
    mount({ rows: [{ kind: "channel", name: "tg" }], supportsScope: false });

    expect(bar().queryByRole("button", { name: /everywhere/i })).toBeNull();
    fireEvent.click(bar().getByRole("button", { name: /^enabled$/i }));

    await waitFor(() => expect(resources.enable).toHaveBeenCalledWith("channel", "tg"));
    expect(scope.put).not.toHaveBeenCalled();
  });

  test("one failed row does not abort the rest, and the partial is reported", async () => {
    resources.disable.mockImplementation((_kind: string, name: string) =>
      name === "writing"
        ? Promise.reject(new ApiError("RESOURCE_NOT_FOUND", "gone"))
        : Promise.resolve(undefined),
    );
    const { onDone } = mount();

    fireEvent.click(bar().getByRole("button", { name: /^disabled$/i }));

    // Both attempted — allSettled, not Promise.all.
    await waitFor(() => expect(resources.disable).toHaveBeenCalledTimes(2));
    // One summary toast, naming the split; never silence, never one per row.
    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError.mock.calls[0][0]).toMatch(/1 succeeded, 1 failed/i);
    expect(toastSuccess).not.toHaveBeenCalled();
    // The selection still clears: the bar must not sit stuck with no message.
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  test("a row that enables but fails its scope write counts as failed, not half-done", async () => {
    resources.enable.mockResolvedValue(undefined);
    scope.put.mockImplementation((_kind: string, name: string) =>
      name === "writing"
        ? Promise.reject(new ApiError("VALIDATION_ERROR", "bad"))
        : Promise.resolve(undefined),
    );
    mount();

    fireEvent.click(bar().getByRole("button", { name: /everywhere/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError.mock.calls[0][0]).toMatch(/1 succeeded, 1 failed/i);
  });

  test("all rows succeeding reports a single success summary", async () => {
    resources.disable.mockResolvedValue(undefined);
    mount();

    fireEvent.click(bar().getByRole("button", { name: /^disabled$/i }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledTimes(1));
    expect(toastSuccess.mock.calls[0][0]).toMatch(/2 succeeded/i);
    expect(toastError).not.toHaveBeenCalled();
  });

  test("the batch refreshes the generic lists plus the kind's own key, once each", async () => {
    resources.disable.mockResolvedValue(undefined);
    const { qc } = mount({ invalidate: [["skills"]] });
    const invalidate = vi.spyOn(qc, "invalidateQueries");

    fireEvent.click(bar().getByRole("button", { name: /^disabled$/i }));

    await waitFor(() => expect(invalidate).toHaveBeenCalled());
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["resources"]));
    expect(keys).toContain(JSON.stringify(["scope"]));
    expect(keys).toContain(JSON.stringify(["skills"]));
  });
});
