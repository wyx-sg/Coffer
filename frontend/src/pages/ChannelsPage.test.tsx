// frontend/src/pages/ChannelsPage.test.tsx
//
// The channels list surface (spec channels). We mock the data hook + the two
// heavy children (dialog, table) so the test asserts ChannelsPage's own
// branching (skeleton / error / empty-welcome / populated) and that the Add
// action opens the dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ChannelsPage } from "./ChannelsPage";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";

vi.mock("@/lib/hooks/useChannels", () => ({ useChannels: vi.fn() }));
vi.mock("@/components/channel/AddChannelDialog", () => ({
  AddChannelDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="add-dialog" /> : null,
}));
vi.mock("@/components/channel/ChannelsTable", () => ({
  ChannelsTable: ({ items, isLoading }: { items: ResourceOut[]; isLoading?: boolean }) => (
    <div data-testid="channels-table" data-loading={isLoading ? "true" : "false"}>
      {items.map((r) => (
        // Keyed on the uid like the real table's rowKey — the name is a label
        // the owner may change, and React keys have to outlive that.
        <span key={r.uid}>{r.name}</span>
      ))}
    </div>
  ),
}));

const { useChannels } = await import("@/lib/hooks/useChannels");
const useChannelsMock = vi.mocked(useChannels);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

/** A channel row as the list hands it over: an opaque uid, a readable name,
 *  and a `default_agent` holding an agent's uid rather than a provider key. */
function channel(uid: string, name: string): ResourceOut {
  return {
    uid,
    name,
    kind: "channel",
    config: { channel_type: "telegram", default_agent: "u-6c1d0b83" },
    enabled: true,
  } as unknown as ResourceOut;
}

function stubQuery(opts: { data?: ResourceOut[]; isPending?: boolean; error?: unknown }) {
  useChannelsMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof useChannels>);
}

describe("ChannelsPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("keeps the header up and hands the table isLoading while the query is pending", () => {
    stubQuery({ isPending: true });
    render(wrap(<ChannelsPage />));
    // No bare "Loading…" card: the title stays mounted over a loading table.
    expect(screen.getByRole("heading", { name: /channels/i })).toBeInTheDocument();
    expect(screen.getByTestId("channels-table")).toHaveAttribute("data-loading", "true");
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });

  test("shows the error card with the translated message when the query errors", () => {
    stubQuery({ error: new ApiError("BOOM", "kaboom") });
    render(wrap(<ChannelsPage />));
    expect(screen.getByText(/failed to load channels/i)).toBeInTheDocument();
    expect(screen.getByText(/kaboom/i)).toBeInTheDocument();
  });

  test("shows the welcome panel (and no table) when there are no channels", () => {
    stubQuery({ data: [] });
    render(wrap(<ChannelsPage />));
    expect(screen.queryByTestId("channels-table")).not.toBeInTheDocument();
    // The empty state's Add call-to-action opens the dialog too.
    fireEvent.click(screen.getByRole("button", { name: /add channel/i }));
    expect(screen.getByTestId("add-dialog")).toBeInTheDocument();
  });

  test("renders the table and the header Add button opens the dialog", () => {
    stubQuery({ data: [channel("u-3d9a1f77", "tg"), channel("u-c0be4512", "st")] });
    render(wrap(<ChannelsPage />));
    expect(screen.getByTestId("channels-table")).toBeInTheDocument();
    expect(screen.getByText("tg")).toBeInTheDocument();
    expect(screen.getByText("st")).toBeInTheDocument();
    expect(screen.queryByTestId("add-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add channel/i }));
    expect(screen.getByTestId("add-dialog")).toBeInTheDocument();
  });
});
