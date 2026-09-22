// What starts Coffer's daemon and what ends it, from the page that sets it.
//
// The two rows are one request, and the thing worth pinning is that the card
// believes the daemon's answer rather than the click: a host with no launchd
// to install into reports the toggle back off, and a card that kept showing
// it on would be telling the user their daemon starts at login when it does
// not (spec daemon FR-028).
import { describe, expect, test, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonResidencySettings } from "./DaemonResidencySettings";

const getMock = vi.fn();
const putMock = vi.fn();
vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({ GET: getMock, PUT: putMock }),
  resetApiClient: vi.fn(),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  getMock.mockReset();
  putMock.mockReset();
});

test("shows what the daemon reports, not a guess", async () => {
  getMock.mockResolvedValue({
    data: {
      login_service_supported: true,
      login_service_installed: true,
      idle_shutdown_hours: 12,
    },
  });

  render(wrap(<DaemonResidencySettings />));

  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  await waitFor(() => expect(toggle).toBeChecked());
});

test("sends both halves in one request", async () => {
  getMock.mockResolvedValue({
    data: {
      login_service_supported: true,
      login_service_installed: false,
      idle_shutdown_hours: 12,
    },
  });
  putMock.mockResolvedValue({
    data: {
      login_service_supported: true,
      login_service_installed: true,
      idle_shutdown_hours: 12,
    },
  });

  render(wrap(<DaemonResidencySettings />));
  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  await waitFor(() => expect(toggle).not.toBeChecked());

  fireEvent.click(toggle);

  await waitFor(() =>
    expect(putMock).toHaveBeenCalledWith("/daemon/residency", {
      body: { login_service_installed: true, idle_shutdown_hours: 12 },
    }),
  );
});

test("a host with no launchd reports the toggle back off, and the card believes it", async () => {
  getMock.mockResolvedValue({
    data: {
      login_service_supported: false,
      login_service_installed: false,
      idle_shutdown_hours: 12,
    },
  });

  render(wrap(<DaemonResidencySettings />));

  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  // Unavailable is a different claim from off: the control says so rather
  // than inviting a click that cannot do anything.
  await waitFor(() => expect(toggle).toBeDisabled());
  expect(screen.getByText(/only available on macos/i)).toBeInTheDocument();
});

describe("the idle window", () => {
  test("offers never as its own option, not as zero", async () => {
    getMock.mockResolvedValue({
      data: {
        login_service_supported: true,
        login_service_installed: true,
        idle_shutdown_hours: null,
      },
    });

    render(wrap(<DaemonResidencySettings />));

    // `null` is "never stand down", and rendering it as a number would make
    // the one setting that turns the behaviour off look like the shortest
    // possible window.
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /stand down after/i })).toHaveTextContent(
        /never/i,
      ),
    );
  });
});

test("a failed save puts the control back — it never left the daemon unchanged and looking changed", async () => {
  getMock.mockResolvedValue({
    data: {
      login_service_supported: true,
      login_service_installed: false,
      idle_shutdown_hours: 12,
    },
  });
  putMock.mockResolvedValue({ error: { error: { code: "INTERNAL_ERROR", message: "nope" } } });

  render(wrap(<DaemonResidencySettings />));
  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  await waitFor(() => expect(toggle).not.toBeChecked());

  fireEvent.click(toggle);

  // The error is shown AND the switch is back off: the two together are the
  // honest report. Either alone is a lie.
  await waitFor(() => expect(screen.getByText(/unexpected error/i)).toBeInTheDocument());
  expect(toggle).not.toBeChecked();
});
