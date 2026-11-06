// src/components/clis/AddCliDialog.test.tsx — Add a command-line tool by hand: what Coffer found before saving, the body sent, the failures, and editing.
//
// Real QueryClientProvider; only the api module is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { DEMO_ADDED, GH_READY } from "@/test/cliFixtures";
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
    expect(api.preview).toHaveBeenCalledWith("jq");
    expect(api.add).not.toHaveBeenCalled();
  });

  test("a tool that is not on this machine can still be added", async () => {
    api.preview.mockResolvedValue({
      command: "ghost",
      path: null,
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
    type("Display name", "JSON");
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(api.add).toHaveBeenCalledWith({
        command: "jq",
        title: "JSON",
        description: null,
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
      existing: DEMO_ADDED,
    });
    expect(screen.getByLabelText("Command")).toBeDisabled();
    expect(screen.getByLabelText("Command")).toHaveValue("demo");
    expect(screen.getByText("Fixed — Coffer finds the tool by it.")).toBeInTheDocument();
    expect(screen.getByText("Edit demo")).toBeInTheDocument();
    // Coffer checks no login and reads no version, so there is no field for either.
    expect(screen.queryByLabelText("Login check")).toBeNull();
    expect(screen.queryByLabelText("Minimum version")).toBeNull();
    expect(api.preview).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Display name")).toHaveValue("Demo tool");
    type("Display name", "");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.edit).toHaveBeenCalledWith("demo", {
        title: null,
        description: "A tool the person added themselves.",
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a tool a skill requires edits every field and sends only what changed", async () => {
    api.edit.mockResolvedValue({ ...GH_READY, description: "Opens issues." });
    const { onOpenChange } = renderDialog({ existing: GH_READY });
    expect(screen.getByText("Edit gh")).toBeInTheDocument();
    expect(screen.getByLabelText("Command")).toBeDisabled();
    expect(screen.getByText(/What you change here replaces what they say/)).toBeInTheDocument();
    expect(screen.getByLabelText("Display name")).toHaveValue("GitHub CLI");
    type("Description", "  Opens issues.  ");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.edit).toHaveBeenCalledWith("gh", {
        description: "Opens issues.",
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
