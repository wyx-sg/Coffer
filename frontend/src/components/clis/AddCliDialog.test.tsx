// src/components/clis/AddCliDialog.test.tsx — Add a command-line tool by hand: what Coffer found before saving, the body sent, the failures, and editing.
//
// Real QueryClientProvider; only the api module is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { DEMO_ADDED } from "@/test/cliFixtures";
import { AddCliDialog } from "./AddCliDialog";

vi.mock("@/lib/api/clis", () => ({
  clisApi: { add: vi.fn(), preview: vi.fn(), edit: vi.fn(), list: vi.fn() },
}));
const { clisApi } = await import("@/lib/api/clis");
const api = vi.mocked(clisApi);

function renderDialog(props: Partial<React.ComponentProps<typeof AddCliDialog>> = {}) {
  const onOpenChange = vi.fn();
  const onSaved = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AddCliDialog open onOpenChange={onOpenChange} onSaved={onSaved} {...props} />
    </QueryClientProvider>,
  );
  return { onOpenChange, onSaved };
}

const type = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  api.preview.mockResolvedValue({
    command: "jq",
    path: "/usr/bin/jq",
    version: "1.7.1",
    added: false,
    required: false,
  });
});
afterEach(() => vi.clearAllMocks());

describe("AddCliDialog", () => {
  acceptance("web-ui", "Add CLI shows what Coffer found before anything is saved", async () => {
    renderDialog();
    type("Command", "jq");
    const found = await screen.findByTestId("cli-found");
    expect(found).toHaveTextContent("/usr/bin/jq");
    expect(found).toHaveTextContent("1.7.1");
    expect(api.preview).toHaveBeenCalledWith("jq");
    expect(api.add).not.toHaveBeenCalled();
  });

  test("a tool that is not on this machine can still be added", async () => {
    api.preview.mockResolvedValue({
      command: "ghost",
      path: null,
      version: null,
      added: false,
      required: false,
    });
    renderDialog();
    type("Command", "ghost");
    expect(await screen.findByText(/ghost isn’t on this machine yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeEnabled();
  });

  test("says when a skill or MCP server already requires the command", async () => {
    api.preview.mockResolvedValue({
      command: "jq",
      path: "/usr/bin/jq",
      version: "1.7.1",
      added: false,
      required: true,
    });
    renderDialog();
    type("Command", "jq");
    expect(
      await screen.findByText(/Already listed — a skill or MCP server needs it/),
    ).toBeInTheDocument();
  });

  test("sends only what was filled in, then closes and reports the command", async () => {
    api.add.mockResolvedValue({ ...DEMO_ADDED, command: "jq" });
    const { onOpenChange, onSaved } = renderDialog();
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    type("Command", "  jq ");
    type("Minimum version", "1.6");
    type("Login check", "jq auth status");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(api.add).toHaveBeenCalledWith({
        command: "jq",
        title: null,
        description: null,
        min_version: "1.6",
        login_check: "jq auth status",
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("jq"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("a refused declaration stays open with the reason", async () => {
    api.add.mockRejectedValue(new ApiError("CLI_TOOL_EXISTS", "already added"));
    const { onOpenChange } = renderDialog();
    type("Command", "jq");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("That command-line tool is already added")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    // The failure stays in the dialog and the primary button becomes Retry.
    expect(screen.getByText("Couldn’t add jq")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
  });

  test("editing keeps the command fixed and sends the fields as a change", async () => {
    api.edit.mockResolvedValue(DEMO_ADDED);
    const { onOpenChange } = renderDialog({
      existing: {
        ...DEMO_ADDED,
        min_version: "2.0",
        login: { state: null, check: ["demo", "auth"], command: null },
      },
    });
    expect(screen.getByLabelText("Command")).toBeDisabled();
    expect(screen.getByLabelText("Command")).toHaveValue("demo");
    expect(screen.getByText("Fixed — Coffer finds the tool by it.")).toBeInTheDocument();
    expect(screen.getByText("Edit demo")).toBeInTheDocument();
    expect(screen.getByLabelText("Login check")).toHaveValue("demo auth");
    expect(api.preview).not.toHaveBeenCalled();
    type("Title", "");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.edit).toHaveBeenCalledWith("demo", {
        title: null,
        description: "A tool the person added themselves.",
        min_version: "2.0",
        login_check: "demo auth",
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
