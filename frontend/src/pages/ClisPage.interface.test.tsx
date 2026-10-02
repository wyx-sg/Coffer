// src/pages/ClisPage.interface.test.tsx — the CLIs page for tools added by hand and the Commands tab: the merged list, the tool's whole interface, its states.
//
// Real QueryClientProvider and the real page; only the api module is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import type { CliInterface } from "@/lib/api/clis";
import { ApiError } from "@/lib/api/errors";
import { DEMO_ADDED, DEMO_INTERFACE, GH_OUTDATED, NOT_READ, UV_READY } from "@/test/cliFixtures";
import { ClisPage } from "./ClisPage";

vi.mock("@/lib/api/clis", () => ({
  clisApi: {
    list: vi.fn(),
    checkAll: vi.fn(),
    get: vi.fn(),
    add: vi.fn(),
    preview: vi.fn(),
    edit: vi.fn(),
    remove: vi.fn(),
    interface: vi.fn(),
    readInterface: vi.fn(),
  },
}));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);

function Where() {
  const { pathname, search } = useLocation();
  return <div data-testid="where">{pathname + search}</div>;
}

function renderPage(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/clis" element={<ClisPage />} />
              <Route path="/clis/:command" element={<ClisPage />} />
              <Route path="/clis/:command/:tab" element={<ClisPage />} />
            </Routes>
            <Where />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const tree = () => screen.getByRole("tree");
const treeItem = (line: string) => within(tree()).getByRole("treeitem", { name: line });

beforeEach(() => {
  api.list.mockResolvedValue({ items: [GH_OUTDATED, DEMO_ADDED, UV_READY], warnings: [] });
  api.get.mockResolvedValue(DEMO_ADDED);
  api.interface.mockResolvedValue(DEMO_INTERFACE);
  api.readInterface.mockResolvedValue(DEMO_INTERFACE);
});
afterEach(() => vi.clearAllMocks());

describe("the merged list", () => {
  test("a tool added by hand is listed beside the ones a skill requires, tagged Added", async () => {
    renderPage("/clis");
    await screen.findByRole("region", { name: "Ready" });
    const ready = within(screen.getByRole("region", { name: "Ready" }));
    const row = ready.getByRole("button", { name: /demo/ });
    expect(row).toHaveTextContent("Added");
    expect(ready.getByRole("button", { name: /uv/ })).toHaveTextContent("1 skill");
  });

  test("an added tool's header says so, offers Edit and Remove, and Needed by shows a dash", async () => {
    renderPage("/clis/demo");
    expect(await screen.findByText("Demo tool · added by you")).toBeInTheDocument();
    expect(screen.getByText("A tool the person added themselves.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
    expect(screen.getByText("Added by you")).toBeInTheDocument();
  });

  test("a tool only a skill requires has no Edit or Remove", async () => {
    renderPage("/clis/gh");
    await screen.findByRole("heading", { level: 2, name: "gh" });
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
  });

  test("removing an added tool asks first and returns to the list", async () => {
    api.remove.mockResolvedValue(undefined);
    renderPage("/clis/demo");
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(screen.getByText("Remove demo?")).toBeInTheDocument();
    expect(api.remove).not.toHaveBeenCalled();
    const dialog = within(screen.getByRole("dialog"));
    fireEvent.click(dialog.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("demo"));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/clis"));
  });
});

describe("the Commands tab", () => {
  test("shows the tool's command tree and the open command's usage and options", async () => {
    renderPage("/clis/demo/commands");
    await screen.findByRole("tree");
    expect(
      within(tree())
        .getAllByRole("treeitem")
        .map((i) => i.getAttribute("aria-label")),
    ).toEqual(["demo", "demo init", "demo run"]);
    // the tool itself is open: usage and its options table
    const node = within(screen.getByTestId("cli-node"));
    expect(node.getByText("demo [OPTIONS] COMMAND [ARGS]...")).toBeInTheDocument();
    expect(node.getByText("-v, --verbose")).toBeInTheDocument();
    expect(node.getByText("Be loud.")).toBeInTheDocument();
    // a subcommand opens from the tree, and its address carries it
    fireEvent.click(treeItem("demo init"));
    expect(screen.getByTestId("where")).toHaveTextContent("/clis/demo/commands?node=init");
    expect(within(screen.getByTestId("cli-node")).getByText("--force")).toBeInTheDocument();
    expect(within(screen.getByTestId("cli-node")).getByText("false")).toBeInTheDocument();
    fireEvent.click(treeItem("demo run"));
    const run = within(screen.getByTestId("cli-node"));
    expect(run.getByText("TARGET")).toBeInTheDocument();
    expect(run.getByText("required")).toBeInTheDocument();
  });

  test("subcommands of the open command open it in the tree", async () => {
    renderPage("/clis/demo/commands");
    await screen.findByRole("tree");
    fireEvent.click(within(screen.getByTestId("cli-node")).getByRole("button", { name: "run" }));
    expect(screen.getByTestId("where")).toHaveTextContent("?node=run");
  });

  test("a deep link opens the node in ?node=", async () => {
    renderPage("/clis/demo/commands?node=run");
    await screen.findByRole("tree");
    expect(treeItem("demo run")).toHaveAttribute("aria-selected", "true");
  });

  test("the filter keeps matches and the commands above them", async () => {
    renderPage("/clis/demo/commands");
    await screen.findByRole("tree");
    fireEvent.change(screen.getByRole("textbox", { name: "Filter this tool's commands" }), {
      target: { value: "overwrite" },
    });
    expect(
      within(tree())
        .getAllByRole("treeitem")
        .map((i) => i.getAttribute("aria-label")),
    ).toEqual(["demo", "demo init"]);
    fireEvent.change(screen.getByRole("textbox", { name: "Filter this tool's commands" }), {
      target: { value: "zzz" },
    });
    expect(screen.getByText("No command matches")).toBeInTheDocument();
  });

  test("Raw help shows what the tool printed, and hides it again", async () => {
    renderPage("/clis/demo/commands");
    await screen.findByRole("tree");
    fireEvent.click(screen.getByRole("button", { name: "Raw help" }));
    expect(screen.getByText(/A demo tool\.\s+Usage: demo/)).toBeInTheDocument();
    expect(screen.queryByText("Be loud.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Hide raw help" }));
    expect(screen.getByText("Be loud.")).toBeInTheDocument();
  });

  test("a help the parser could not structure is shown raw at once", async () => {
    const odd: CliInterface = {
      ...DEMO_INTERFACE,
      nodes: [{ ...DEMO_INTERFACE.nodes[0]!, structured: false, raw: "Some free text help." }],
    };
    api.interface.mockResolvedValue(odd);
    renderPage("/clis/demo/commands");
    expect(await screen.findByText("Some free text help.")).toBeInTheDocument();
  });

  test("copies a command's full line", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderPage("/clis/demo/commands?node=init");
    await screen.findByRole("tree");
    fireEvent.click(within(tree()).getByRole("button", { name: "Copy demo init" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("demo init"));
  });

  test("a tool whose help was never read is read by itself, with a loading line", async () => {
    api.interface.mockResolvedValue(NOT_READ);
    let finish: (v: CliInterface) => void = () => {};
    api.readInterface.mockReturnValue(new Promise((r) => (finish = r)));
    renderPage("/clis/demo/commands");
    expect(
      await screen.findByRole("status", { name: "Reading the tool's help…" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(api.readInterface).toHaveBeenCalledTimes(1));
    finish(DEMO_INTERFACE);
    await screen.findByRole("tree");
    expect(api.readInterface).toHaveBeenCalledTimes(1);
  });

  test("opening the tool reads its help even while Overview is showing", async () => {
    api.interface.mockResolvedValue(NOT_READ);
    renderPage("/clis/demo");
    await screen.findByRole("heading", { level: 2, name: "demo" });
    await waitFor(() => expect(api.readInterface).toHaveBeenCalledTimes(1));
  });

  test("Read again reads the help again", async () => {
    renderPage("/clis/demo/commands");
    await screen.findByRole("tree");
    expect(api.readInterface).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Read again" }));
    await waitFor(() => expect(api.readInterface).toHaveBeenCalledTimes(1));
  });

  test("a read that fails says so and offers Retry", async () => {
    api.interface.mockResolvedValue(NOT_READ);
    api.readInterface.mockRejectedValueOnce(new ApiError("INTERNAL_ERROR", "boom"));
    renderPage("/clis/demo/commands");
    expect(await screen.findByText("Couldn't read the commands")).toBeInTheDocument();
    api.readInterface.mockResolvedValue(DEMO_INTERFACE);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("tree");
  });

  test("a tool with no help says why and still offers Read again", async () => {
    api.interface.mockResolvedValue({
      ...NOT_READ,
      status: "no_help",
      message: "/bin/demo --help printed nothing.",
    });
    renderPage("/clis/demo/commands");
    expect(await screen.findByText("No help to read")).toBeInTheDocument();
    expect(screen.getByText("/bin/demo --help printed nothing.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Read again" })).toBeInTheDocument();
  });

  test("a tree cut by the bounds says so", async () => {
    api.interface.mockResolvedValue({ ...DEMO_INTERFACE, incomplete: true });
    renderPage("/clis/demo/commands");
    expect(await screen.findByText(/the tree stops at three levels/)).toBeInTheDocument();
  });

  test("a node with no help shows the reason", async () => {
    const broken: CliInterface = {
      ...DEMO_INTERFACE,
      nodes: [
        DEMO_INTERFACE.nodes[0]!,
        { ...DEMO_INTERFACE.nodes[1]!, structured: false, raw: "", error: "timed out" },
      ],
    };
    api.interface.mockResolvedValue(broken);
    renderPage("/clis/demo/commands?node=init");
    expect(await screen.findByText("No help printed: timed out")).toBeInTheDocument();
  });

  test("a tool that is not on this machine has no commands to read", async () => {
    const missing = { ...DEMO_ADDED, status: "missing" as const, path: null, version: null };
    api.list.mockResolvedValue({ items: [missing], warnings: [] });
    api.get.mockResolvedValue(missing);
    renderPage("/clis/demo/commands");
    expect(await screen.findByText("Not found on this machine")).toBeInTheDocument();
    expect(api.interface).not.toHaveBeenCalled();
    expect(api.readInterface).not.toHaveBeenCalled();
  });
});
