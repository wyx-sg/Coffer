// frontend/src/pages/MachineDetailPage.test.tsx
//
// One machine's activation slice (spec 010-sync amendment, Task 18): which
// agents/mcp_servers/skills/channels are active on that machine. We mock
// useMachineSlice so the page doesn't depend on a running daemon.
//
// Carries the acceptance marker for spec scenario "the fleet view renders
// any machine's activation slice".
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MachineDetailPage } from "./MachineDetailPage";
import { acceptance } from "@/test/acceptance";
import type { MachineSlice } from "@/lib/hooks/useMachines";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useMachines", () => ({
  useMachineSlice: vi.fn(),
}));

const machinesHooks = await import("@/lib/hooks/useMachines");
const useMachineSliceMock = vi.mocked(machinesHooks.useMachineSlice);

const REMOTE_SLICE: MachineSlice = {
  machine: {
    machine_id: "01BBBBBBBBBBBBBBBBBBBBBBBB",
    display_name: "laptop",
    platform: "darwin",
    os_version: "24.0.0",
    coffer_version: "0.1.1",
    last_sync_at: "2026-07-10T12:00:00+00:00",
    is_local: false,
  },
  agents: [
    { name: "claude-code", active: true },
    { name: "codex", active: false },
  ],
  mcp_servers: [{ name: "figma", active: true, agents: ["claude-code"] }],
  skills: [{ name: "pdf-tools", active: false, agents: [] }],
  channels: [{ name: "telegram", active: true }],
};

const LOCAL_SLICE: MachineSlice = {
  ...REMOTE_SLICE,
  machine: {
    ...REMOTE_SLICE.machine,
    machine_id: "01AAAAAAAAAAAAAAAAAAAAAAAA",
    display_name: "studio",
    is_local: true,
  },
};

function mockSlice(data: MachineSlice | undefined, opts: { error?: unknown } = {}) {
  useMachineSliceMock.mockReturnValue({
    data,
    isPending: false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof machinesHooks.useMachineSlice>);
}

function renderAt(id = REMOTE_SLICE.machine.machine_id) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/machines/${id}`]}>
        <Routes>
          <Route path="/machines/:id" element={<MachineDetailPage />} />
          <Route path="/machines" element={<div>machines list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

acceptance("010-sync", "the fleet view renders any machine's activation slice", async () => {
  mockSlice(REMOTE_SLICE);
  renderAt();

  // Title renders the machine's display name.
  expect(screen.getByRole("heading", { name: "laptop" })).toBeInTheDocument();

  // Four sections render.
  expect(screen.getByText(/agents/i)).toBeInTheDocument();
  expect(screen.getByText(/mcp servers/i)).toBeInTheDocument();
  expect(screen.getByText(/skills/i)).toBeInTheDocument();
  expect(screen.getByText(/channels/i)).toBeInTheDocument();

  // Row entries render across every axis. "claude-code" appears twice — once
  // as the agents-section row name, once as figma's bound-agent text — so
  // use getAllByText there.
  expect(screen.getAllByText("claude-code").length).toBeGreaterThan(0);
  expect(screen.getByText("codex")).toBeInTheDocument();
  expect(screen.getByText("figma")).toBeInTheDocument();
  expect(screen.getByText("pdf-tools")).toBeInTheDocument();
  expect(screen.getByText("telegram")).toBeInTheDocument();

  // Rows link out to the resource's own detail page.
  const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
  expect(links).toContain("/agents/claude-code");
  expect(links).toContain("/mcp-servers/mcp_server/figma");
  expect(links).toContain("/skills/pdf-tools");
  expect(links).toContain("/channels/telegram");
});

describe("MachineDetailPage", () => {
  test("inactive rows are badged inactive, active rows badged active", () => {
    mockSlice(REMOTE_SLICE);
    renderAt();

    const codexRow = screen.getByText("codex").closest("a") as HTMLElement;
    expect(codexRow).toHaveTextContent(/inactive/i);

    // "claude-code" also appears as figma's bound-agent text; scope to the
    // agent row's name element (font-medium) to disambiguate.
    const claudeRow = screen
      .getByText("claude-code", { selector: "p.font-medium" })
      .closest("a") as HTMLElement;
    expect(claudeRow).toHaveTextContent(/^(?!.*inactive).*active/i);
  });

  test("dual-axis rows (mcp servers, skills) show the bound agent names", () => {
    mockSlice(REMOTE_SLICE);
    renderAt();

    const figmaRow = screen.getByText("figma").closest("a") as HTMLElement;
    expect(figmaRow).toHaveTextContent("claude-code");
  });

  test("a remote machine shows the intent-only hint", () => {
    mockSlice(REMOTE_SLICE);
    renderAt();
    expect(screen.getByText(/intent/i)).toBeInTheDocument();
  });

  test("the local machine does not show the intent-only hint", () => {
    mockSlice(LOCAL_SLICE);
    renderAt(LOCAL_SLICE.machine.machine_id);
    expect(screen.queryByText(/intent/i)).not.toBeInTheDocument();
    expect(screen.getByText(/this machine/i)).toBeInTheDocument();
  });

  test("shows the error card when the slice fails to load (e.g. unknown machine)", () => {
    mockSlice(undefined, { error: new ApiError("BOOM", "no such machine") });
    renderAt();
    expect(screen.getByText(/failed to load machines/i)).toBeInTheDocument();
    expect(screen.getByText("no such machine")).toBeInTheDocument();
  });
});
