// frontend/src/components/reach/BulkReachActions.test.tsx
//
// The reach choice over a table selection: a 340 popover with the same three
// modes, a tri-state box per agent over the selection ("2 of 3", "→ 3 of 3"),
// and — unlike one resource — a bulk change WAITS FOR APPLY. A partial failure
// is written in the popover with Retry for the failed items only; it never
// toasts.
import { afterEach, describe, expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { PropsWithChildren } from "react";

import { acceptance } from "@/test/acceptance";
import { ApiError } from "@/lib/api/errors";
import { BulkReachActions } from "./BulkReachActions";

const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";

vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn(), rename: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({
    data: [
      { uid: CLAUDE, name: "claude", type: "claude_code" },
      { uid: CODEX, name: "codex", type: "codex" },
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
const disable = vi.mocked(resourcesApi.disable);
const enable = vi.mocked(resourcesApi.enable);
const put = vi.mocked(scopeApi.put);

// Claude reaches all three; Codex only the first.
const ROWS = [
  {
    kind: "skill",
    uid: "u-skill-a",
    name: "frontend-design",
    enabled: true,
    scope: { agents: [CLAUDE, CODEX] },
  },
  { kind: "skill", uid: "u-skill-b", name: "pdf", enabled: true, scope: { agents: [CLAUDE] } },
  {
    kind: "skill",
    uid: "u-skill-c",
    name: "release-notes",
    enabled: true,
    scope: { agents: [CLAUDE] },
  },
];

let qc: QueryClient;
function mount(props: Partial<Parameters<typeof BulkReachActions>[0]> = {}) {
  const onDone = vi.fn();
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <BulkReachActions rows={ROWS} onDone={onDone} {...props} />
    </QueryClientProvider>,
  );
  return onDone;
}

const trigger = () => within(screen.getByTestId("bulk-reach-control")).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });
const box = (name: string) =>
  within(screen.getByTestId(`scope-agent-${name}`)).getByRole("checkbox") as HTMLInputElement;
const apply = () => fireEvent.click(screen.getByRole("button", { name: "Apply" }));

afterEach(() => {
  vi.clearAllMocks();
  disable.mockResolvedValue(undefined as never);
  enable.mockResolvedValue(undefined as never);
  put.mockResolvedValue(undefined as never);
});
disable.mockResolvedValue(undefined as never);
enable.mockResolvedValue(undefined as never);
put.mockResolvedValue(undefined as never);

describe("the popover", () => {
  test("the trigger is a Reach button; the popover is 340 wide with three unpicked modes", () => {
    mount();
    expect(trigger()).toHaveTextContent("Reach");
    openPanel();
    expect(screen.getByRole("dialog")).toHaveClass("w-[340px]");
    expect(screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual([
      "Off",
      "All agents",
      "Chosen agents",
    ]);
    expect(
      screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked),
    ).toHaveLength(0);
    expect(screen.getByText("Reach for 3 selected")).toBeInTheDocument();
  });

  test("shows each agent's count over the selection and a dash for 'some'", () => {
    mount();
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    expect(
      within(screen.getByTestId("scope-agent-claude")).getByText("3 of 3"),
    ).toBeInTheDocument();
    expect(within(screen.getByTestId("scope-agent-codex")).getByText("1 of 3")).toBeInTheDocument();
    expect(box("claude")).toBeChecked();
    expect(box("codex").indeterminate).toBe(true);
  });

  test("clicking a partly-ticked agent cycles dash → ticked → empty → dash, old → new counts", () => {
    mount();
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    const row = within(screen.getByTestId("scope-agent-codex"));
    fireEvent.click(box("codex"));
    expect(row.getByText(/1 of 3/)).toBeInTheDocument();
    expect(row.getByText(/→ 3 of 3/)).toBeInTheDocument();
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("1 change · codex gets 2 more");
    fireEvent.click(box("codex"));
    expect(row.getByText(/→ 0 of 3/)).toBeInTheDocument();
    fireEvent.click(box("codex"));
    expect(row.queryByText(/→/)).toBeNull();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  test("the list is dimmed and frozen until Chosen agents is picked", () => {
    mount();
    openPanel();
    expect(box("codex")).toBeDisabled();
  });
});

describe("Apply writes; nothing is written before it", () => {
  test("Off turns off every selected item once Apply is pressed", async () => {
    const onDone = mount();
    openPanel();
    fireEvent.click(choice(/^off$/i));
    expect(disable).not.toHaveBeenCalled();
    apply();
    await waitFor(() => expect(disable).toHaveBeenCalledTimes(3));
    expect(put).not.toHaveBeenCalled();
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(toastSuccess).toHaveBeenCalledOnce();
  });

  test("All agents skips items that already are, and clears the scope of the rest", async () => {
    mount({ rows: [...ROWS, { kind: "skill", uid: "u-skill-d", enabled: true, scope: null }] });
    openPanel();
    fireEvent.click(choice(/^all agents$/i));
    apply();
    await waitFor(() => expect(put).toHaveBeenCalledTimes(3));
    expect(put.mock.calls.every((c) => c[1] === null)).toBe(true);
    expect(put.mock.calls.map((c) => c[0])).not.toContain("u-skill-d");
  });

  test("Chosen agents writes each item's own new list, only where it changes", async () => {
    mount();
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    fireEvent.click(box("codex")); // → ticked for all
    apply();
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    const written = Object.fromEntries(put.mock.calls.map((c) => [c[0], c[1]]));
    expect(written["u-skill-a"]).toBeUndefined(); // already reached Codex
    expect(written["u-skill-b"]).toEqual({ agents: [CLAUDE, CODEX] });
    expect(written["u-skill-c"]).toEqual({ agents: [CLAUDE, CODEX] });
  });

  test("a row left with no agent is switched off, said in the preview, scope kept", async () => {
    mount();
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    fireEvent.click(box("claude")); // → unticked for all
    expect(screen.getByTestId("reach-summary")).toHaveTextContent("2 left with no agent turn off");
    apply();
    await waitFor(() => expect(disable).toHaveBeenCalledTimes(2));
    expect(disable.mock.calls.map((c) => c[0]).sort()).toEqual(["u-skill-b", "u-skill-c"]);
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("u-skill-a", { agents: [CODEX] });
  });

  test("Cancel drops every staged box and writes nothing", () => {
    mount();
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    fireEvent.click(box("codex"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(put).not.toHaveBeenCalled();
    openPanel();
    expect(
      screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked),
    ).toHaveLength(0);
  });

  test("refreshes the generic lists and the kind's own once the batch settles", async () => {
    mount({ invalidate: [["skills"]] });
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    openPanel();
    fireEvent.click(choice(/^off$/i));
    apply();
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
    disable.mockImplementation((uid: string) =>
      uid === "u-skill-c"
        ? Promise.reject(new ApiError("RESOURCE_NOT_FOUND", "read-only"))
        : Promise.resolve(undefined as never),
    );
    const onDone = mount();

    // Starts blank: the button names the action and no mode is picked.
    expect(trigger()).toHaveTextContent("Reach");
    openPanel();
    expect(
      screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked),
    ).toHaveLength(0);

    fireEvent.click(choice(/^off$/i));
    apply();

    // The failure is written in the popover — never a toast.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Applied to 2 of 3");
    expect(alert).toHaveTextContent("release-notes");
    expect(toastError).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();

    // Retry resends the failed item only; success closes and clears the selection.
    disable.mockResolvedValue(undefined as never);
    disable.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(disable).toHaveBeenCalledTimes(1));
    expect(disable).toHaveBeenCalledWith("u-skill-c");
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
  },
);

test("a scope that saved but could not be delivered to an agent is a failure of that item (4.3.31)", async () => {
  put.mockImplementation(((uid: string) =>
    Promise.resolve({
      delivery:
        uid === "u-skill-c"
          ? [{ agent_uid: CODEX, agent_name: "codex", ok: false, reason: "~/.codex is read-only" }]
          : [{ agent_uid: CODEX, agent_name: "codex", ok: true, reason: null }],
    })) as never);
  const onDone = mount();
  openPanel();
  fireEvent.click(choice(/chosen agents/i));
  fireEvent.click(box("codex"));
  apply();

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Applied to 1 of 2");
  expect(alert).toHaveTextContent("release-notes");
  expect(alert).toHaveTextContent("~/.codex is read-only");
  expect(toastError).not.toHaveBeenCalled();
  expect(onDone).not.toHaveBeenCalled();
});
