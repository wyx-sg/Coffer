// frontend/src/pages/MemoryDetailPage.test.tsx
//
// One partition's page (spec memory "Present a partition as its memories"):
// it opens on Memories — its memories beside the selected one, a collapsed
// read-only Retired group with reasons, a meta line naming the agents and
// the update time — and shows none of the agents' own memory: no file tree,
// no MEMORY.md / RETIRED.md / .raw/, no native path. Delivered, at
// /memory/<uid>/delivered, shows each agent's session-start text with an
// agent switch and no hook state. Only the api modules are mocked.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import {
  COFFER,
  DELIVERED,
  DELIVERIES,
  FILES,
  GONE,
  NATIVE_PATH,
  NODE_NOTE,
  NOTES,
  PORT_NOTE,
  RETIRED,
} from "@/components/memory/memoryTestData";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { MemoryDetailPage } from "@/pages/MemoryDetailPage";
import { MemoryPage } from "@/pages/MemoryPage";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/memory", () => ({
  listPartitions: vi.fn(),
  listNotes: vi.fn(),
  getNote: vi.fn(),
  listRetired: vi.fn(),
  listPartitionFiles: vi.fn(),
  getDelivered: vi.fn(),
  getDeliveries: vi.fn(),
  getReading: vi.fn(async () => ({ read_at: null, failures: [] })),
  sync: vi.fn(),
}));
vi.mock("@/lib/api/upkeep", () => ({ listUpkeepRuns: vi.fn() }));
vi.mock("@/lib/api/internalEngine", () => ({ internalEngineApi: { get: vi.fn() } }));
vi.mock("@/lib/api/resources", () => ({ resourcesApi: { remove: vi.fn() } }));
// The first-run welcome lists the connected agents; none here.
vi.mock("@/lib/api/agents", () => ({ agentsApi: { list: vi.fn(async () => ({ items: [] })) } }));

const api = await import("@/lib/api/memory");
const { listUpkeepRuns } = await import("@/lib/api/upkeep");
const { internalEngineApi } = await import("@/lib/api/internalEngine");
const { resourcesApi } = await import("@/lib/api/resources");

function stub({
  partitions = [COFFER],
  model = "claude-sonnet",
  running = false,
}: { partitions?: PartitionOut[]; model?: string | null; running?: boolean } = {}) {
  vi.mocked(api.listPartitions).mockResolvedValue({ partitions });
  vi.mocked(api.listNotes).mockResolvedValue(NOTES);
  vi.mocked(api.getNote).mockImplementation(async (_uid, slug) =>
    slug === PORT_NOTE.slug ? PORT_NOTE : NODE_NOTE,
  );
  vi.mocked(api.listRetired).mockResolvedValue(RETIRED);
  vi.mocked(api.listPartitionFiles).mockResolvedValue(FILES);
  vi.mocked(api.getDelivered).mockResolvedValue(DELIVERED);
  vi.mocked(api.getDeliveries).mockResolvedValue(DELIVERIES);
  vi.mocked(listUpkeepRuns).mockResolvedValue({
    runs: running
      ? [
          {
            kind: "memory",
            name: COFFER.uid,
            started_at: "2026-09-30T08:00:00Z",
            done: null,
            total: null,
          },
        ]
      : [],
  });
  vi.mocked(internalEngineApi.get).mockResolvedValue({ model } as Awaited<
    ReturnType<typeof internalEngineApi.get>
  >);
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/memory/:uid" element={<MemoryDetailPage />} />
            <Route path="/memory/:uid/:tab" element={<MemoryDetailPage />} />
            <Route path="*" element={null} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** Radix tabs activate on mousedown, not click. */
function openTab(name: RegExp) {
  fireEvent.mouseDown(screen.getByRole("tab", { name }), { button: 0 });
}

function assertNoAgentOwnMemory() {
  const text = document.body.textContent ?? "";
  expect(text).not.toContain("MEMORY.md");
  expect(text).not.toContain("RETIRED.md");
  expect(text).not.toContain(".raw");
  expect(text).not.toContain(NATIVE_PATH);
  expect(text).not.toContain("/.codex/memories");
  expect(screen.queryByRole("tree")).toBeNull();
}

describe("MemoryDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stub();
  });

  test("opens on Memories with the first memory selected and its meta line", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    expect(
      await screen.findByRole("tab", { name: "Memories", selected: true }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: NODE_NOTE.title })).toBeInTheDocument();
    const meta = await screen.findByTestId("memory-meta");
    expect(meta).toHaveTextContent(/^Learned by Claude Code, Codex · updated 2026-09-26/);
    // The body is rendered Markdown, with no frontmatter in it.
    const pane = screen.getByTestId("memory-pane");
    expect(within(pane).getByText("Node 20")).toBeInTheDocument();
    expect(pane).not.toHaveTextContent(/origins:|native_path|---/);
    // The header: repository path and the memory count; open / reveal on the file.
    expect(screen.getByText(/^~\/work\/coffer · 2 memories · distilled /)).toBeInTheDocument();
    expect(within(pane).getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(within(pane).getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    assertNoAgentOwnMemory();
  });

  test("choosing a memory puts it in the URL and shows it", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: /Daemon port is fixed at 8000/ }));
    expect(await screen.findByRole("heading", { name: PORT_NOTE.title })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(`?memory=${PORT_NOTE.slug}`);
    expect(await screen.findByTestId("memory-meta")).toHaveTextContent(/^Learned by Claude Code ·/);
  });

  test("retired memories are a collapsed, read-only group with their reasons", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    const group = await screen.findByTestId("memory-retired");
    const toggle = within(group).getByRole("button", { name: /retired/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveTextContent(/Retired\s*1/);
    expect(within(group).queryByText(RETIRED.retired[0].title)).toBeNull();
    fireEvent.click(toggle);
    expect(within(group).getByText(RETIRED.retired[0].title)).toBeInTheDocument();
    expect(within(group).getByText(RETIRED.retired[0].reason)).toBeInTheDocument();
    expect(within(group).queryByRole("button", { name: /restore/i })).toBeNull();
  });

  test("no per-memory action and no status or reach control", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    const pane = await screen.findByTestId("memory-pane");
    const list = screen.getByRole("list", { name: "Memories" });
    // The header's Edit is the partition's title, not a memory's.
    for (const region of [pane, list, screen.getByTestId("memory-retired")]) {
      expect(
        within(region).queryByRole("button", { name: /^(edit|delete|restore|hide|pin)\b/i }),
      ).toBeNull();
    }
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  test("a partition with no memories says so and offers Update memory", async () => {
    vi.mocked(api.listNotes).mockResolvedValue({ notes: [] });
    renderAt(`/memory/${COFFER.uid}`);
    expect(await screen.findByText("No memories for coffer yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(2);
  });

  test("without Coffer's model, a quiet notice links to Settings › General", async () => {
    stub({ model: null });
    renderAt(`/memory/${COFFER.uid}`);
    const notice = await screen.findByTestId("memory-no-model");
    expect(notice).toHaveTextContent(/each agent's entry becomes its own memory/);
    fireEvent.click(within(notice).getByRole("button", { name: /Settings › General/ }));
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/settings/general"),
    );
  });

  test("with Coffer's model set, there is no such notice", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    await screen.findByTestId("memory-pane");
    expect(screen.queryByTestId("memory-no-model")).toBeNull();
  });

  test("Delivered lives at /memory/<uid>/delivered with an agent switch", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    await screen.findByTestId("memory-pane");
    openTab(/delivered/i);
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(`/memory/${COFFER.uid}/delivered`),
    );
    const text = await screen.findByTestId("memory-delivered-text");
    // Claude Code first, as on the Agents page.
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.textContent)).toEqual(["Claude Code", "Codex"]);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(text.textContent).toBe(DELIVERED.agents[1].text);
    expect(
      screen.getByText("What a session in ~/work/coffer starts with · read-only"),
    ).toBeInTheDocument();
    expect(screen.getByText(`${DELIVERED.agents[1].text.length} characters`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /codex/i }));
    expect(screen.getByTestId("memory-delivered-text").textContent).toBe(DELIVERED.agents[0].text);
    expect(document.body.textContent).not.toMatch(/hook|repair|stale/i);
  });

  test("Delivered with no agent connected says so", async () => {
    vi.mocked(api.getDelivered).mockResolvedValue({ partition: "coffer", agents: [] });
    renderAt(`/memory/${COFFER.uid}/delivered`);
    expect(await screen.findByText(/No agent is connected to Coffer/)).toBeInTheDocument();
  });

  test("the running state is the daemon's, matched by the partition's uid", async () => {
    stub({ running: true });
    renderAt(`/memory/${COFFER.uid}`);
    const button = await screen.findByRole("button", { name: /updating/i });
    expect(button).toBeDisabled();
  });

  test("the ⋯ menu offers Delete only while the repository is gone", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: /more actions for coffer/i }));
    expect(
      await screen.findByRole("menuitem", { name: /reveal partition folder/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /copy path/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /delete partition/i })).toBeNull();
  });

  test("deleting an unresolvable partition confirms, then returns to Memory", async () => {
    stub({ partitions: [GONE] });
    vi.mocked(resourcesApi.remove).mockResolvedValue(undefined);
    renderAt(`/memory/${GONE.uid}`);
    expect(await screen.findByTestId("partition-unresolvable-badge")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /more actions for old-prototype/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /delete partition/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete old-prototype?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete partition" }));
    await waitFor(() => expect(resourcesApi.remove).toHaveBeenCalledWith(GONE.uid));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/memory$/));
  });

  test("offers the way back to the partitions list", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    expect(await screen.findByRole("link", { name: /back to memory/i })).toBeInTheDocument();
  });

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", async () => {
    // The partition's page half: no reach or status button in the header.
    renderAt(`/memory/${COFFER.uid}`);
    await screen.findByRole("heading", { name: "coffer" });
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(enabled|disabled|every agent)$/i })).toBeNull();
  });
});

acceptance("memory", "browse a partition as a file tree with a read-only preview", async () => {
  vi.clearAllMocks();
  // With no partitions: the first-run welcome, no table.
  stub({ partitions: [] });
  const first = renderAt("/memory");
  expect(await screen.findByText("No agent memory to read")).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
  first.unmount();

  // With one distilled partition: the table.
  stub();
  const second = renderAt("/memory");
  expect(await screen.findByRole("table")).toBeInTheDocument();
  second.unmount();

  // Its page lists its memories beside the chosen one.
  renderAt(`/memory/${COFFER.uid}`);
  const list = await screen.findByRole("list", { name: "Memories" });
  expect(within(list).getByText(NOTES.notes[0].title)).toBeInTheDocument();
  expect(within(list).getByText(NOTES.notes[1].title)).toBeInTheDocument();
  const meta = await screen.findByTestId("memory-meta");
  expect(meta).toHaveTextContent("Claude Code");
  expect(meta).toHaveTextContent("Codex");
  expect(meta).toHaveTextContent(/updated 2026-09-26/);
  expect(screen.getByTestId("memory-pane")).not.toHaveTextContent(/origins:|---/);

  // The retired memory is in a collapsed Retired group with its reason.
  const group = screen.getByTestId("memory-retired");
  const toggle = within(group).getByRole("button", { name: /retired/i });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  expect(within(group).getByText(RETIRED.retired[0].reason)).toBeInTheDocument();

  // None of the agents' own memory; open and reveal, and no edit or delete.
  assertNoAgentOwnMemory();
  const pane = screen.getByTestId("memory-pane");
  expect(within(pane).getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  expect(within(pane).getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  expect(within(pane).queryByRole("button", { name: /^(edit|delete)\b/i })).toBeNull();
  expect(within(list).queryByRole("button", { name: /^(edit|delete)\b/i })).toBeNull();
});
