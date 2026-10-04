// PriceRefreshSetting: the daily price-list refresh switch under Speech-to-text (spec provider-switching).
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { PriceList } from "@/lib/api/providers";
import { acceptance } from "@/test/acceptance";
import "@/i18n";
import { PriceRefreshSetting } from "./PriceRefreshSetting";

vi.mock("@/lib/api/providers", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/providers")>()),
  providersApi: { priceList: vi.fn(), setPriceRefresh: vi.fn() },
}));
const { providersApi } = await import("@/lib/api/providers");
const api = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const doc = (over: Partial<PriceList> = {}): PriceList => ({
  version: "genai-prices@x",
  updated: "2026-09-30",
  origin: "bundled",
  refresh: true,
  pinned_off: false,
  last_attempt_at: null,
  last_error: null,
  ...over,
});

function renderRow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceRefreshSetting />
    </QueryClientProvider>,
  );
}

describe("PriceRefreshSetting", () => {
  acceptance("provider-switching", "the refresh can be turned off", async () => {
    api.priceList.mockResolvedValue(doc());
    api.setPriceRefresh.mockResolvedValue(doc({ refresh: false }));
    renderRow();
    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toBeChecked());
    expect(
      screen.getByText(/Using the list shipped with Coffer, updated .*2026/),
    ).toBeInTheDocument();
    fireEvent.click(toggle);
    await waitFor(() => expect(api.setPriceRefresh).toHaveBeenCalledWith(false));
    await waitFor(() => expect(screen.getByRole("switch")).not.toBeChecked());
  });

  test("a refreshed list, a failure and an environment pin say so", async () => {
    api.priceList.mockResolvedValue(
      doc({ origin: "refreshed", pinned_off: true, last_error: "boom" }),
    );
    renderRow();
    expect(await screen.findByText(/Using the list refreshed .*2026/)).toBeInTheDocument();
    expect(screen.getByText(/Turned off by COFFER_PRICE_REFRESH/)).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeDisabled();
  });
});
