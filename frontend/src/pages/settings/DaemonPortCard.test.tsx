// frontend/src/pages/settings/DaemonPortCard.test.tsx
//
// The daemon-port card (spec mcp-gateway FR-028). Like the backup card's test
// this one drives the real hooks against a stubbed `fetch`, because what
// matters is the wire: which body each save sends, and which saves never leave
// the browser at all.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
}

const requests = (method: string) => calls.filter((c) => c.method === method);
const fixedSwitch = () => screen.getByLabelText(/use a fixed port/i);
const portInput = () => screen.getByLabelText(/^port$/i);
const saveButton = () => screen.getByRole("button", { name: /^save$/i });

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

  test("saving a fixed port PUTs it", async () => {
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    fireEvent.change(portInput(), { target: { value: "8123" } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(requests("PUT")).toHaveLength(1));
    expect(requests("PUT")[0].body).toEqual({ port: 8123 });
  });

  test("turning the switch off saves null — back to automatic selection", async () => {
    settings = { configured_port: 8123, effective_port: 8123, restart_required: false };
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    fireEvent.click(saveButton());

    await waitFor(() => expect(requests("PUT")).toHaveLength(1));
    expect(requests("PUT")[0].body).toEqual({ port: null });
  });

  test("an out-of-range port never leaves the browser", async () => {
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    fireEvent.change(portInput(), { target: { value: "80" } });
    fireEvent.click(saveButton());

    expect(await screen.findByText(/between 1024 and 65535/i)).toBeInTheDocument();
    expect(requests("PUT")).toHaveLength(0);
  });

  test("a port the daemon rejects is surfaced as it came back", async () => {
    putStatus = { status: 400, code: "VALIDATION_ERROR", message: "port must be 1024-65535" };
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    fireEvent.change(portInput(), { target: { value: "9999" } });
    fireEvent.click(saveButton());

    expect(await screen.findByText(/port must be 1024-65535/i)).toBeInTheDocument();
  });

  test("a restart-pending save leaves a persistent note naming the command", async () => {
    await renderLoaded();
    expect(screen.queryByTestId("daemon-restart-note")).not.toBeInTheDocument();

    fireEvent.click(fixedSwitch());
    fireEvent.change(portInput(), { target: { value: "8123" } });
    fireEvent.click(saveButton());

    const note = await screen.findByTestId("daemon-restart-note");
    expect(note).toHaveTextContent("coffer daemon restart");
    // The note must not offer to restart from here: this page is served by the
    // daemon it would be killing.
    expect(screen.queryByRole("button", { name: /restart/i })).not.toBeInTheDocument();
  });

  test("a save that needs no restart leaves no note", async () => {
    settings = { configured_port: null, effective_port: 8003, restart_required: false };
    await renderLoaded();
    fireEvent.click(fixedSwitch());
    fireEvent.click(saveButton()); // 8003 — the port already being served

    await waitFor(() => expect(requests("PUT")).toHaveLength(1));
    expect(screen.queryByTestId("daemon-restart-note")).not.toBeInTheDocument();
  });
});
