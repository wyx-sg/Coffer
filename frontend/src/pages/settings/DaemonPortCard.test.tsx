// frontend/src/pages/settings/DaemonPortCard.test.tsx
//
// The daemon-port card (spec mcp-gateway FR-028). Like the backup card's test
// this one drives the real hooks against a stubbed `fetch`, because what
// matters is the wire: which body each save sends, and which saves never leave
// the browser at all.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { DaemonPortSettings } from "@/lib/api/daemonSettings";
import { DaemonPortCard } from "./DaemonPortCard";

interface Recorded {
  method: string;
  path: string;
  body: Record<string, unknown> | undefined;
}

let calls: Recorded[];
let settings: DaemonPortSettings;
/** What the daemon answers a PUT with; null means "echo what it was sent". */
let putReply: DaemonPortSettings | null;
let putStatus: { status: number; code: string; message: string } | null;

function installFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname.replace("/api/v1", "");
      const method = init?.method ?? "GET";
      const body = init?.body
        ? (JSON.parse(String(init.body)) as Record<string, unknown>)
        : undefined;
      calls.push({ method, path, body });

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "content-type": "application/json" },
        });

      if (path !== "/settings/daemon") return new Response("not found", { status: 404 });
      if (method === "GET") return json(settings);
      if (method === "PUT") {
        if (putStatus) {
          const { status, code, message } = putStatus;
          return json({ error: { code, message } }, status);
        }
        const port = (body?.port ?? null) as number | null;
        settings = putReply ?? {
          configured_port: port,
          effective_port: settings.effective_port,
          restart_required: port !== null && port !== settings.effective_port,
        };
        return json(settings);
      }
      return new Response("not found", { status: 404 });
    }),
  );
}

function renderCard() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DaemonPortCard />
    </QueryClientProvider>,
  );
}

/** Wait until the daemon's answer has landed in the card. */
async function renderLoaded() {
  renderCard();
  await waitFor(() => expect(screen.getByTestId("daemon-address")).not.toHaveTextContent("—"));
  // The address paints as soon as the query resolves, but the switch and the
  // port field are seeded by an effect that runs after that commit. Waiting on
  // the address alone can land between the two, and a click arriving there
  // reads the pre-seed state — the switch reads as off with a configured port,
  // and a save then sends that port instead of null. Flush the pending effects
  // so every test starts from the seeded form.
  await act(async () => {});
}

const requests = (method: string) => calls.filter((c) => c.method === method);
const fixedSwitch = () => screen.getByLabelText(/use a fixed port/i);
const portInput = () => screen.getByLabelText(/^port$/i);

beforeEach(() => {
  calls = [];
  settings = { configured_port: null, effective_port: 8003, restart_required: false };
  putReply = null;
  putStatus = null;
  installFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DaemonPortCard", () => {
  test("shows the address to bookmark, built from the serving port", async () => {
    await renderLoaded();
    expect(screen.getByTestId("daemon-address")).toHaveTextContent("http://127.0.0.1:8003");
  });

  test("automatic selection hides the port field until the switch goes on", async () => {
    await renderLoaded();
    expect(fixedSwitch()).not.toBeChecked();
    expect(screen.queryByLabelText(/^port$/i)).not.toBeInTheDocument();

    fireEvent.click(fixedSwitch());
    // Seeded with the port already serving this page — the one value that
    // cannot break the address shown above.
    expect(portInput()).toHaveValue(8003);
  });

  test("a configured port opens with the switch on and that port in the field", async () => {
    settings = { configured_port: 8123, effective_port: 8123, restart_required: false };
    await renderLoaded();
    expect(fixedSwitch()).toBeChecked();
    expect(portInput()).toHaveValue(8123);
  });

  test("a fixed port is written when the field is committed, with no Save button", async () => {
    await renderLoaded();
    // The page has no Save button at all — everything on it saves as you
    // change it, which is the rule the rest of Settings already follows.
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();

    fireEvent.click(fixedSwitch());
    await waitFor(() => expect(requests("PUT")).toHaveLength(1));

    fireEvent.change(portInput(), { target: { value: "8123" } });
    // Typing alone must not write — 8, 81, 812 are all valid-looking ports.
    expect(requests("PUT")).toHaveLength(1);

    fireEvent.blur(portInput());
    await waitFor(() => expect(requests("PUT")).toHaveLength(2));
    expect(requests("PUT")[1].body).toEqual({ port: 8123 });
  });

  test("turning the switch off saves null — back to automatic selection", async () => {
    settings = { configured_port: 8123, effective_port: 8123, restart_required: false };
    await renderLoaded();
    fireEvent.click(fixedSwitch());

    await waitFor(() => expect(requests("PUT")).toHaveLength(1));
    expect(requests("PUT")[0].body).toEqual({ port: null });
  });

  test("an out-of-range port never leaves the browser", async () => {
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    await waitFor(() => expect(requests("PUT")).toHaveLength(1));

    fireEvent.change(portInput(), { target: { value: "80" } });
    fireEvent.blur(portInput());

    expect(await screen.findByText(/between 1024 and 65535/i)).toBeInTheDocument();
    // Only the switch's own write; the bad port was refused in the browser.
    expect(requests("PUT")).toHaveLength(1);
  });

  test("a port the daemon rejects is surfaced as it came back", async () => {
    putStatus = { status: 400, code: "VALIDATION_ERROR", message: "port must be 1024-65535" };
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    fireEvent.change(portInput(), { target: { value: "9999" } });
    fireEvent.blur(portInput());

    expect(await screen.findByText(/port must be 1024-65535/i)).toBeInTheDocument();
  });

  test("a restart-pending save leaves a persistent note naming the command", async () => {
    await renderLoaded();
    expect(screen.queryByTestId("daemon-restart-note")).not.toBeInTheDocument();

    fireEvent.click(fixedSwitch());
    fireEvent.change(portInput(), { target: { value: "8123" } });
    fireEvent.blur(portInput());

    const note = await screen.findByTestId("daemon-restart-note");
    expect(note).toHaveTextContent("coffer daemon restart");
    // The note must not offer to restart from here: this page is served by the
    // daemon it would be killing.
    expect(screen.queryByRole("button", { name: /restart/i })).not.toBeInTheDocument();
  });

  test("a save that needs no restart leaves no note", async () => {
    settings = { configured_port: null, effective_port: 8003, restart_required: false };
    await renderLoaded();
    // Turning the switch on pins the port already being served, so it writes
    // on its own — nothing to type, nothing to confirm.
    fireEvent.click(fixedSwitch());

    await waitFor(() => expect(requests("PUT")).toHaveLength(1));
    expect(requests("PUT")[0].body).toEqual({ port: 8003 });
    expect(screen.queryByTestId("daemon-restart-note")).not.toBeInTheDocument();
  });
});
