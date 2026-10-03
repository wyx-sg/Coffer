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
import { ApiError } from "@/lib/api/errors";
import { MemoryDetailPage } from "@/pages/MemoryDetailPage";
import { MemoryPage } from "@/pages/MemoryPage";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/memory", () => ({
  listPartitions: vi.fn(),
  listNotes: vi.fn(),
  getNote: vi.fn(),
  saveNote: vi.fn(),
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

  // Opens on Memories with the first memory selected and its meta line: the
  // page half of the scenario (the REST note route keeps the native paths —
  // test_memory_routes.py).
  acceptance("memory", "provenance paths stay in the data, not on the page", async () => {
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
    // The header: the name alone, then repository path, memory count, age.
    const title = screen.getByRole("heading", { level: 1, name: "coffer" });
    const header = title.closest("header") as HTMLElement;
    expect(header).toHaveTextContent(/~\/work\/coffer · 2 memories · distilled /);
    // No back link, no Experimental tag, no Automatic control, no file action on a memory.
    expect(screen.queryByText(/‹ Memory/)).toBeNull();
    expect(screen.queryByText("Experimental")).toBeNull();
    expect(screen.queryByRole("button", { name: /automatic/i })).toBeNull();
    expect(within(pane).queryByRole("button", { name: /open in editor|reveal/i })).toBeNull();
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

  test("Edit is the only per-memory action, and there is no status or reach control", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    const pane = await screen.findByTestId("memory-pane");
    const list = screen.getByRole("list", { name: "Memories" });
    expect(
      within(pane)
        .getAllByRole("button")
        .map((b) => b.textContent?.trim()),
    ).toEqual(["Edit"]);
    for (const region of [pane, list, screen.getByTestId("memory-retired")]) {
      expect(
        within(region).queryByRole("button", { name: /^(delete|restore|hide|pin)\b/i }),
      ).toBeNull();
    }
    // A retired memory offers no Edit.
    expect(
      within(screen.getByTestId("memory-retired")).queryByRole("button", { name: /^edit/i }),
    ).toBeNull();
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  test("a partition with no memories says so and offers Update memory", async () => {
    vi.mocked(api.listNotes).mockResolvedValue({ notes: [] });
    renderAt(`/memory/${COFFER.uid}`);
    expect(await screen.findByText("No memories for coffer yet")).toBeInTheDocument();
    // Only the header carries Update memory: the empty state has none, and no
    // list column is drawn beside it (board 5.2.08).
    expect(screen.getAllByRole("button", { name: /update memory/i })).toHaveLength(1);
    expect(screen.queryByRole("list", { name: "Memories" })).toBeNull();
  });

  test("without Coffer's model, a quiet notice links to Settings › General", async () => {
    stub({ model: null });
    renderAt(`/memory/${COFFER.uid}`);
    const notice = await screen.findByTestId("memory-no-model");
    expect(notice).toHaveTextContent(/each agent’s entry stays its own memory/);
    expect(notice).toHaveTextContent(/until it is set in Settings › General\./);
    fireEvent.click(within(notice).getByRole("button", { name: "Open Settings" }));
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/settings/general"),
    );
  });

  acceptance(
    "memory",
    "a partition's page names the partition and offers no way back",
    async () => {
      stub({ model: null });
      renderAt(`/memory/${COFFER.uid}`);
      expect(await screen.findByRole("heading", { name: "coffer" })).toBeInTheDocument();
      expect(screen.queryByText("Experimental")).toBeNull();
      expect(screen.queryByRole("link", { name: /back/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /^back/i })).toBeNull();
      expect(screen.queryByTestId("memory-automatic")).toBeNull();
      expect(screen.getByText(/memories/)).toBeInTheDocument();
      // Without Coffer's engine a banner names it and offers Open Settings.
      const notice = await screen.findByTestId("memory-no-model");
      expect(notice).toHaveTextContent(/each agent’s entry stays its own memory/);
      expect(within(notice).getByRole("button", { name: "Open Settings" })).toBeInTheDocument();
    },
  );

  test("with Coffer's model set, there is no such notice", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    await screen.findByTestId("memory-pane");
    expect(screen.queryByTestId("memory-no-model")).toBeNull();
  });

  // Delivered lives at /memory/<uid>/delivered with an agent switch.
  acceptance("memory", "a partition has a memories tab and a delivered tab", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    expect(
      await screen.findByRole("tab", { name: "Memories", selected: true }),
    ).toBeInTheDocument();
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
    expect(screen.getByText(/ characters · nothing trimmed$/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /codex/i }));
    expect(screen.getByTestId("memory-delivered-text").textContent).toBe(DELIVERED.agents[0].text);
    expect(document.body.textContent).not.toMatch(/hook|repair|stale/i);
  });

  acceptance(
    "web-ui",
    "a partition's delivered tab shows each agent's session-start text",
    async () => {
      renderAt(`/memory/${COFFER.uid}/delivered`);
      const text = await screen.findByTestId("memory-delivered-text");
      expect(text.textContent).toBe(DELIVERED.agents[1].text);
      expect(
        screen.getByText("What a session in ~/work/coffer starts with · read-only"),
      ).toBeInTheDocument();
      // Read-only: no field to edit and no action on the text.
      expect(screen.queryByRole("textbox")).toBeNull();
      fireEvent.click(screen.getByRole("radio", { name: /codex/i }));
      expect(screen.getByTestId("memory-delivered-text").textContent).toBe(
        DELIVERED.agents[0].text,
      );
    },
  );

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

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", async () => {
    // The partition's page half: no reach or status button in the header.
    renderAt(`/memory/${COFFER.uid}`);
    await screen.findByRole("heading", { name: "coffer" });
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(enabled|disabled|every agent)$/i })).toBeNull();
  });
});

describe("editing a memory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stub();
  });

  const body = () => screen.getByRole("textbox", { name: `Edit ${NODE_NOTE.title}` });

  acceptance("memory", "the selected memory is edited in place", async () => {
    const saved = {
      ...NODE_NOTE,
      body: "Run the tests on Node 20.",
      fingerprint: "fp-node-2",
      updated_at: "2026-10-04T10:00:00Z",
    };
    vi.mocked(api.saveNote).mockImplementation(async () => {
      // From here the daemon reads the saved note.
      vi.mocked(api.getNote).mockResolvedValue(saved);
      return saved;
    });
    renderAt(`/memory/${COFFER.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    // The body alone is edited: no frontmatter in the text.
    expect(body()).toHaveValue(NODE_NOTE.body);
    expect(body()).not.toHaveValue(expect.stringContaining("origins:"));
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(body(), { target: { value: "Run the tests on Node 20." } });
    fireEvent.click(save);
    await waitFor(() =>
      expect(api.saveNote).toHaveBeenCalledWith(COFFER.uid, NODE_NOTE.slug, {
        body: "Run the tests on Node 20.",
        expected_fingerprint: "fp-node-1",
      }),
    );
    // Back to the rendered memory, with the saved body and a refreshed time.
    expect(await screen.findByText("Run the tests on Node 20.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByTestId("memory-meta")).toHaveTextContent(/updated 2026-10-04/);
  });

  acceptance("memory", "a save over a note that changed is refused with the current text", async () => {
    vi.mocked(api.saveNote).mockRejectedValue(
      new ApiError("MEMORY_NOTE_CONFLICT", "changed", {
        saved: false,
        current_body: "Distil rewrote this.",
        current_fingerprint: "fp-node-9",
      }),
    );
    renderAt(`/memory/${COFFER.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(body(), { target: { value: "My version." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This memory changed on disk while you were editing");
    // The draft is intact and Save stays off until the person chooses.
    expect(body()).toHaveValue("My version.");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    // Compare shows the disk's text against mine; saving over names the new fingerprint.
    fireEvent.click(within(alert).getByRole("button", { name: "Compare" }));
    expect(await screen.findByText("Distil rewrote this.")).toBeInTheDocument();
    vi.mocked(api.saveNote).mockResolvedValueOnce({ ...NODE_NOTE, body: "My version." });
    fireEvent.click(screen.getByRole("button", { name: "Save my edit" }));
    await waitFor(() =>
      expect(api.saveNote).toHaveBeenLastCalledWith(COFFER.uid, NODE_NOTE.slug, {
        body: "My version.",
        expected_fingerprint: "fp-node-9",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
  });

  test("Reload takes the disk's version after asking", async () => {
    vi.mocked(api.saveNote).mockRejectedValue(
      new ApiError("MEMORY_NOTE_CONFLICT", "changed", {
        saved: false,
        current_body: "Distil rewrote this.",
        current_fingerprint: "fp-node-9",
      }),
    );
    renderAt(`/memory/${COFFER.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(body(), { target: { value: "My version." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "Reload…" }));
    const dialog = await screen.findByRole("dialog");
    expect(api.getNote).toHaveBeenCalledTimes(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(api.getNote).toHaveBeenCalledTimes(2);
  });

  test("Discard with changes asks first", async () => {
    renderAt(`/memory/${COFFER.uid}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(body(), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /discard/i }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(api.saveNote).not.toHaveBeenCalled();
  });
});

acceptance("memory", "browse a partition's memories with a read-only preview", async () => {
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

  // None of the agents' own memory, and no file action, edit or delete on a memory.
  assertNoAgentOwnMemory();
  const pane = screen.getByTestId("memory-pane");
  expect(within(pane).queryByRole("button", { name: /open in editor|reveal/i })).toBeNull();
  expect(within(pane).getByRole("button", { name: "Edit" })).toBeInTheDocument();
  expect(within(pane).queryByRole("button", { name: /^delete\b/i })).toBeNull();
  expect(within(list).queryByRole("button", { name: /^(edit|delete)\b/i })).toBeNull();
});
