// frontend/src/components/reach/BulkReachActions.test.tsx
//
// The bulk half of the reach control: each choice writes the SAME state to
// EVERY selected row, and partial failure is reported rather than swallowed.
// The old bar offered Enable/Disable only, which could not express the state the
// rows themselves could be in.
//
// Its button cannot state a current reach the way a row's does — a mixed
// selection has none — so it names the action instead, opens with nothing
// chosen, and writes nothing at all if the user picks nothing.
//
// Every request it fans out is addressed by the row's UID alone; the `kind` a
// row carries never reaches the wire, it only says which list key the batch
// refreshes. The fixtures keep uid and name unalike so an assertion that
// reached for the label would fail rather than coincide.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { acceptance } from "@/test/acceptance";
import { BulkReachActions } from "./BulkReachActions";
import { ApiError } from "@/lib/api/errors";

/** The agents the machine knows: the uid a scope stores, and the name the
 *  pick-list rows are labelled by. */
const CLAUDE = "u-agent-7f21";

vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn(), rename: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({
    data: [
      { uid: "u-agent-7f21", name: "claude" },
      { uid: "u-agent-be04", name: "codex" },
    ],
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

/** Two selected skills, by uid. They are labelled "writing" and "reviewing",
 *  which is what the table shows and what nothing below asserts on. */
const WRITING_UID = "u-skill-4e8d";
const REVIEWING_UID = "u-skill-0a13";

const ROWS = [
  { kind: "skill", uid: WRITING_UID },
  { kind: "skill", uid: REVIEWING_UID },
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

/** The bulk bar's one button. */
const trigger = () => within(screen.getByTestId("bulk-reach-control")).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });
const closePanel = () =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
/** One agent's row in the pick-list, by the NAME it is labelled with. */
const agentRow = (name: string) => within(screen.getByTestId(`scope-agent-${name}`));

/** Open the panel and pick one whole-value choice, which also closes it. */
const pick = (label: RegExp) => {
  openPanel();
  fireEvent.click(choice(label));
};

afterEach(() => vi.clearAllMocks());

describe("BulkReachActions", () => {
  test("the button names the action, because a mixed selection has no state to name", async () => {
    // In a row the label IS the current reach. Here it would have to pick one
    // of the states the selection holds and misreport the rest.
    mount();
    expect(trigger()).toHaveTextContent(/set reach/i);
    openPanel();
    for (const label of [/^disabled$/i, /every agent/i, /only selected agents/i]) {
      expect(choice(label)).not.toBeChecked();
    }
  });

  test("dismissing the panel without choosing writes nothing to any row", async () => {
    const { onDone } = mount();
    openPanel();
    closePanel();
    expect(resources.disable).not.toHaveBeenCalled();
    expect(resources.enable).not.toHaveBeenCalled();
    expect(scope.put).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  test("Disabled disables every selected row by uid, and writes no scope", async () => {
    resources.disable.mockResolvedValue(undefined);
    const { onDone } = mount();

    pick(/^disabled$/i);

    await waitFor(() => expect(resources.disable).toHaveBeenCalledTimes(2));
    // The uid is the whole argument: the kind the row carries is for the
    // invalidation, not for the route.
    expect(resources.disable.mock.calls.map((c) => c[0]).sort()).toEqual(
      [REVIEWING_UID, WRITING_UID].sort(),
    );
    expect(scope.put).not.toHaveBeenCalled();
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  test("Everywhere enables each row and clears its scope", async () => {
    resources.enable.mockResolvedValue(undefined);
    scope.put.mockResolvedValue(undefined);
    mount();

    pick(/every agent/i);

    await waitFor(() => expect(scope.put).toHaveBeenCalledTimes(2));
    expect(resources.enable).toHaveBeenCalledTimes(2);
    expect(scope.put.mock.calls.every((c) => c[1] === null)).toBe(true);
  });

  test("Restricted writes the SAME staged scope to every row, once", async () => {
    resources.enable.mockResolvedValue(undefined);
    scope.put.mockResolvedValue(undefined);
    mount();

    openPanel();
    fireEvent.click(choice(/only selected agents/i));
    // The panel opens on an EMPTY draft: a bulk write is a new intent, not an
    // edit of whichever row happened to be first.
    expect(agentRow("claude").getByRole("checkbox")).not.toBeChecked();

    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    expect(scope.put).not.toHaveBeenCalled();

    closePanel();
    await waitFor(() => expect(scope.put).toHaveBeenCalledTimes(2));
    // Ticked by name, written as a uid, addressed by a uid — both halves of
    // the translation in one assertion.
    expect(scope.put.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      [WRITING_UID, { agents: [CLAUDE] }],
      [REVIEWING_UID, { agents: [CLAUDE] }],
    ]);
  });

  test("a kind with no scope gets two choices, and Enabled writes only the flag", async () => {
    resources.enable.mockResolvedValue(undefined);
    const TG_UID = "u-channel-1b77"; // named "tg"
    mount({ rows: [{ kind: "channel", uid: TG_UID }], supportsScope: false });

    openPanel();
    expect(screen.queryByRole("radio", { name: /every agent/i })).toBeNull();
    fireEvent.click(choice(/^enabled$/i));

    await waitFor(() => expect(resources.enable).toHaveBeenCalledWith(TG_UID));
    expect(scope.put).not.toHaveBeenCalled();
  });

  test("one failed row does not abort the rest, and the partial is reported", async () => {
    resources.disable.mockImplementation((uid: string) =>
      uid === WRITING_UID
        ? Promise.reject(new ApiError("RESOURCE_NOT_FOUND", "gone"))
        : Promise.resolve(undefined),
    );
    const { onDone } = mount();

    pick(/^disabled$/i);

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
    scope.put.mockImplementation((uid: string) =>
      uid === WRITING_UID
        ? Promise.reject(new ApiError("VALIDATION_ERROR", "bad"))
        : Promise.resolve(undefined),
    );
    mount();

    pick(/every agent/i);

    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError.mock.calls[0][0]).toMatch(/1 succeeded, 1 failed/i);
  });

  test("all rows succeeding reports a single success summary", async () => {
    resources.disable.mockResolvedValue(undefined);
    mount();

    pick(/^disabled$/i);

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledTimes(1));
    expect(toastSuccess.mock.calls[0][0]).toMatch(/2 succeeded/i);
    expect(toastError).not.toHaveBeenCalled();
  });

  test("the batch refreshes the generic lists plus the kind's own key, once each", async () => {
    resources.disable.mockResolvedValue(undefined);
    const { qc } = mount({ invalidate: [["skills"]] });
    const invalidate = vi.spyOn(qc, "invalidateQueries");

    pick(/^disabled$/i);

    await waitFor(() => expect(invalidate).toHaveBeenCalled());
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["resources"]));
    expect(keys).toContain(JSON.stringify(["scope"]));
    expect(keys).toContain(JSON.stringify(["skills"]));
  });
});

acceptance(
  "web-ui",
  "a bulk reach write starts blank and reports failures in one summary",
  async () => {
    resources.disable.mockImplementation((uid: string) =>
      uid === REVIEWING_UID
        ? Promise.reject(new ApiError("RESOURCE_NOT_FOUND", "gone"))
        : Promise.resolve(undefined),
    );
    mount();

    expect(trigger()).toHaveTextContent("Set reach…");
    openPanel();
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(radios.filter((r) => (r as HTMLInputElement).checked)).toHaveLength(0);

    fireEvent.click(choice(/^disabled$/i));

    await waitFor(() => expect(resources.disable).toHaveBeenCalledTimes(2));
    expect(resources.disable.mock.calls.map((c) => c[0]).sort()).toEqual(
      [WRITING_UID, REVIEWING_UID].sort(),
    );
    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError.mock.calls[0][0]).toMatch(/1 succeeded, 1 failed/i);
    expect(toastSuccess).not.toHaveBeenCalled();
  },
);
