// frontend/src/pages/ChannelsPage.test.tsx
//
// The channels list surface (spec 009). We mock the data hook + the two
// heavy children (dialog, table) so the test asserts ChannelsPage's own
// branching (loading / error / empty-welcome / populated) and that the Add
// action opens the dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ChannelsPage } from "./ChannelsPage";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";

vi.mock("@/lib/hooks/useChannels", () => ({ useChannels: vi.fn() }));
vi.mock("@/kinds/channel/AddChannelDialog", () => ({
  AddChannelDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="add-dialog" /> : null,
}));
vi.mock("@/kinds/channel/ChannelsTable", () => ({
  ChannelsTable: ({ items }: { items: ResourceOut[] }) => (
    <div data-testid="channels-table">
      {items.map((r) => (
        <span key={r.name}>{r.name}</span>
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

function channel(name: string): ResourceOut {
  return {
    name,
    kind: "channel",
    config: { channel_type: "telegram", default_agent: "builtin" },
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

  test("shows the loading card while the query is pending", () => {
    stubQuery({ isPending: true });
    render(wrap(<ChannelsPage />));
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByTestId("channels-table")).not.toBeInTheDocument();
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
    stubQuery({ data: [channel("tg"), channel("st")] });
    render(wrap(<ChannelsPage />));
    expect(screen.getByTestId("channels-table")).toBeInTheDocument();
    expect(screen.getByText("tg")).toBeInTheDocument();
    expect(screen.getByText("st")).toBeInTheDocument();
    expect(screen.queryByTestId("add-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add channel/i }));
    expect(screen.getByTestId("add-dialog")).toBeInTheDocument();
  });
});
