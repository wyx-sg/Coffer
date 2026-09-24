// Whether Coffer's daemon starts at login, from the page that sets it.
//
// The thing worth pinning is that the card believes the daemon's answer rather
// than the click: a host with no launchd to install into reports the toggle
// back off, and a card that kept showing it on would be telling the user their
// daemon starts at login when it does not (spec daemon "Run as a login
// service"). The card offers nothing else — the daemon never stands down on
// its own, so there is no idle window to choose.
import { expect, test, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { acceptance } from "@/test/acceptance";
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
    data: { login_service_supported: true, login_service_installed: true },
  });

  render(wrap(<DaemonResidencySettings />));

  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  await waitFor(() => expect(toggle).toBeChecked());
});

test("a host with no launchd reports the toggle back off, and the card believes it", async () => {
  getMock.mockResolvedValue({
    data: { login_service_supported: false, login_service_installed: false },
  });

  render(wrap(<DaemonResidencySettings />));

  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  // Unavailable is a different claim from off: the control says so rather
  // than inviting a click that cannot do anything.
  await waitFor(() => expect(toggle).toBeDisabled());
  expect(screen.getByText(/only available on macos/i)).toBeInTheDocument();
});

test("nothing is clickable until the daemon has answered", () => {
  // The switch shows a default before the GET lands. A click then would PUT
  // that default over whatever the daemon actually holds.
  getMock.mockReturnValue(new Promise(() => {}));

  render(wrap(<DaemonResidencySettings />));

  expect(screen.getByRole("switch", { name: /start at login/i })).toBeDisabled();
});

acceptance("web-ui", "the general tab sets when the daemon runs", async () => {
  getMock.mockResolvedValue({
    data: { login_service_supported: true, login_service_installed: false },
  });
  // The first write succeeds and the daemon reports what became true; the
  // second is refused.
  putMock
    .mockResolvedValueOnce({
      data: { login_service_supported: true, login_service_installed: true },
    })
    .mockResolvedValueOnce({ error: { error: { code: "INTERNAL_ERROR", message: "nope" } } });

  render(wrap(<DaemonResidencySettings />));
  expect(await screen.findByText("Coffer's daemon")).toBeInTheDocument();

  // The card offers no idle-window or stand-down control: the switch is its
  // one control.
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByText(/stand down/i)).not.toBeInTheDocument();
  expect(screen.getAllByRole("switch")).toHaveLength(1);

  // Start at login: one request carrying login_service_installed and no idle
  // window.
  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  await waitFor(() => expect(toggle).not.toBeDisabled());
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  await waitFor(() => expect(putMock).toHaveBeenCalledTimes(1));
  expect(putMock).toHaveBeenLastCalledWith("/daemon/residency", {
    body: { login_service_installed: true },
  });
  await waitFor(() => expect(toggle).toBeChecked());

  // Turning it off again is refused: the switch goes back to what the daemon
  // last reported and the error is shown beside it.
  await waitFor(() => expect(toggle).not.toBeDisabled());
  fireEvent.click(toggle);
  await waitFor(() => expect(putMock).toHaveBeenCalledTimes(2));
  expect(putMock).toHaveBeenLastCalledWith("/daemon/residency", {
    body: { login_service_installed: false },
  });
  await waitFor(() => expect(screen.getByText(/internal error/i)).toBeInTheDocument());
  expect(toggle).toBeChecked();
});

test("a failed save puts the switch back off and shows the error", async () => {
  getMock.mockResolvedValue({
    data: { login_service_supported: true, login_service_installed: false },
  });
  putMock.mockResolvedValue({ error: { error: { code: "INTERNAL_ERROR", message: "nope" } } });

  render(wrap(<DaemonResidencySettings />));
  const toggle = await screen.findByRole("switch", { name: /start at login/i });
  await waitFor(() => expect(toggle).not.toBeDisabled());

  fireEvent.click(toggle);

  // The error is shown AND the switch is back off: the two together are the
  // honest report. Either alone is a lie.
  await waitFor(() => expect(screen.getByText(/internal error/i)).toBeInTheDocument());
  expect(toggle).not.toBeChecked();
});
