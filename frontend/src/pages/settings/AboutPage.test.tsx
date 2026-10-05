// frontend/src/pages/settings/AboutPage.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { AboutPage } from "./AboutPage";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const STATUS = {
  version: "0.7.42",
  channel: "stable",
  status: "ready",
  started_at: "2026-05-01T08:00:00Z",
  port: 38470,
  executable: "/Applications/Coffer.app/Contents/MacOS/coffer-daemon",
  machine_id: "m-1",
  machine_name: "work-mac",
  features: { knowledge: true, memory: false, sync: true },
  upstream_summary: null,
  pid: 4242,
  commit: "3909da95",
  data_dir: "~/.coffer",
  connected_agents: 1,
};

function mockStatus() {
  getApiClientMock.mockReturnValue({
    GET: vi.fn().mockResolvedValue({ data: STATUS, error: undefined }),
  } as unknown as ReturnType<typeof getApiClient>);
}

describe("AboutPage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  test("shows license and source unconditionally", () => {
    // useDaemonStatus is allowed to be in-flight; the other fields don't depend on it.
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})), // pending forever
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    expect(screen.getByText("AGPL-3.0")).toBeInTheDocument();
    expect(screen.getByText(/github\.com\/wyx-sg\/Coffer/)).toBeInTheDocument();
  });

  test("links the documentation in the interface language", () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})),
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });
    expect(screen.getByRole("link", { name: "Open the docs" })).toHaveAttribute(
      "href",
      "https://wyx-sg.github.io/Coffer/",
    );
  });

  // The About half of the scenario; e2e shell_settings.spec.ts visits every tab
  // for the shutdown control.
  acceptance("web-ui", "settings offers no shutdown control", async () => {
    mockStatus();
    const { container } = render(<AboutPage />, { wrapper: wrap });

    await waitFor(() => {
      expect(screen.getByText("Version 0.7.42")).toBeInTheDocument();
    });
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("License")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    // The details name the build and where its data lives; no release channel is shown.
    expect(screen.getByText("0.7.42 (3909da95)")).toBeInTheDocument();
    expect(screen.getByText("~/.coffer")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/stable/);
    // Copy diagnostics is the one action beside the version; no shutdown or
    // stop control, no language picker and no resource-kind list.
    expect(screen.getByRole("button", { name: /copy diagnostics/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /shut\s*down|stop daemon/i })).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(container.textContent).not.toMatch(/resource kinds/i);
    expect(screen.queryByText("38470")).not.toBeInTheDocument();
  });

  test("falls back to '—' for the version before /daemon/status resolves", () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})),
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    // The version and the data folder both wait for the status probe.
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getByText(/reading the version/i)).toBeInTheDocument();
  });

  acceptance("web-ui", "copy diagnostics carries no secret", async () => {
    mockStatus();
    const injected = window as unknown as { __COFFER_TOKEN__?: string };
    injected.__COFFER_TOKEN__ = "tok-must-not-leak";
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<AboutPage />, { wrapper: wrap });
    await screen.findByText("Version 0.7.42");

    fireEvent.click(screen.getByRole("button", { name: /copy diagnostics/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const text = writeText.mock.calls[0][0] as string;
    expect(text).toContain("Coffer: 0.7.42");
    expect(text).not.toMatch(/channel/i);
    expect(text).toMatch(/Host: browser/);
    expect(text).toContain("Daemon: running on port 38470");
    expect(text).toContain("Features: knowledge, sync");
    expect(text).not.toContain("tok-must-not-leak");
    expect(text).not.toMatch(/token|secret/i);
    delete injected.__COFFER_TOKEN__;
  });
});
