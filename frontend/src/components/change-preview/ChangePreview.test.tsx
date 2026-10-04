// src/components/change-preview/ChangePreview.test.tsx
// Behaviour of the shared change preview across its states, including the web-ui acceptance scenarios.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { ChangePreview, type ChangeItem, type ChangePreviewState } from "./ChangePreview";

const ITEMS: ChangeItem[] = [
  {
    id: "c1",
    agentType: "claude_code",
    path: "~/.claude.json",
    op: "modify",
    added: 2,
    removed: 1,
    diff: [
      { kind: "hunk", text: "@@ −12,6 +12,7 @@ mcpServers" },
      { kind: "context", text: '  "mcpServers": {', oldNo: 12, newNo: 12 },
      { kind: "remove", text: '"url": "http://127.0.0.1:8123/mcp"', oldNo: 14 },
      { kind: "add", text: '"url": "http://127.0.0.1:38470/mcp",', newNo: 14 },
      { kind: "add", text: '"type": "http"', newNo: 15 },
    ],
  },
  { id: "c2", agentType: "claude_code", path: "~/.claude/skills/pdf", op: "add" },
  {
    id: "c3",
    agentType: "codex",
    path: "~/.codex/config.toml",
    op: "modify",
    added: 3,
    diff: [
      { kind: "hunk", text: "@@ −21,2 +21,5 @@" },
      { kind: "add", text: "[mcp_servers.coffer]", newNo: 24 },
    ],
  },
  { id: "c4", agentType: "codex", path: "~/.codex/skills/release-notes", op: "remove" },
];

function renderPreview(
  state: ChangePreviewState,
  overrides: Partial<React.ComponentProps<typeof ChangePreview>> = {},
) {
  const onApply = vi.fn();
  const onRetry = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ChangePreview
      open
      onOpenChange={onOpenChange}
      title="Review changes"
      subtitle="Reconnect agents to Coffer"
      state={state}
      items={ITEMS}
      summaries={[
        { agentType: "claude_code", text: "Its Coffer entry moves to port 38470." },
        { agentType: "codex", text: "Gets the Coffer gateway." },
      ]}
      onApply={onApply}
      onRetry={onRetry}
      {...overrides}
    />,
  );
  return { onApply, onRetry, onOpenChange };
}

function rowOf(path: string): HTMLElement {
  const row = screen.getByText(path, { selector: "li span" }).closest("li");
  if (!row) throw new Error(`no row for ${path}`);
  return row;
}

describe("ChangePreview", () => {
  acceptance("web-ui", "the change preview groups a write by agent and file", () => {
    const { onApply } = renderPreview("ready");
    expect(screen.getByTestId("changes-heading")).toHaveTextContent("Changes · 4");
    expect(screen.queryByTestId("change-summary")).not.toBeInTheDocument();

    // Each file under its agent, with its operation and line counts.
    const claude = screen.getByRole("region", { name: "Claude Code" });
    const codex = screen.getByRole("region", { name: "Codex" });
    expect(within(claude).getAllByRole("listitem")).toHaveLength(2);
    expect(within(codex).getAllByRole("listitem")).toHaveLength(2);
    const claudeJson = within(claude).getByText("~/.claude.json").closest("li") as HTMLElement;
    expect(claudeJson).toHaveTextContent("+2");
    expect(claudeJson).toHaveTextContent("−1");
    expect(within(claudeJson).getByText("Modify")).toBeInTheDocument();
    expect(within(claude).getByText("~/.claude/skills/pdf").closest("li")).toHaveTextContent("Add");
    expect(within(codex).getByText("~/.codex/config.toml").closest("li")).toHaveTextContent("+3");
    expect(
      within(codex).getByText("~/.codex/skills/release-notes").closest("li"),
    ).toHaveTextContent("Remove");

    // Each changed file's diff, in list order.
    const diffs = screen.getAllByRole("region", { name: /^Changes to / });
    expect(diffs.map((d) => d.getAttribute("aria-label"))).toEqual([
      "Changes to ~/.claude.json",
      "Changes to ~/.codex/config.toml",
    ]);
    expect(within(diffs[0]).getByText('"url": "http://127.0.0.1:38470/mcp",')).toBeInTheDocument();
    expect(diffs[0].querySelectorAll('[data-line="add"]')).toHaveLength(2);
    expect(diffs[0].querySelectorAll('[data-line="remove"]')).toHaveLength(1);

    // Plain words first, then the primary action.
    expect(screen.getByText("What will happen")).toBeInTheDocument();
    const apply = screen.getByRole("button", { name: "Apply 4 changes" });
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalledOnce();
  });

  acceptance("web-ui", "a write that failed partway retries only what failed", () => {
    const items: ChangeItem[] = ITEMS.map((item) =>
      item.id === "c3"
        ? { ...item, status: "failed", error: "Permission denied — the file is read-only." }
        : { ...item, status: "applied" },
    );
    const { onRetry, onOpenChange } = renderPreview("failed", { items });

    // It stays open and says what did apply.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("1 of 4 changes failed.");
    expect(banner).toHaveTextContent("The other 3 were applied and stay applied.");

    // The failed change's reason sits under its path.
    const failedRow = rowOf("~/.codex/config.toml");
    expect(failedRow).toHaveAttribute("data-status", "failed");
    expect(within(failedRow).getByText("Failed")).toBeInTheDocument();
    expect(within(failedRow).getByText("Permission denied — the file is read-only.")).toHaveClass(
      "text-danger",
    );
    expect(rowOf("~/.claude.json")).toHaveAttribute("data-status", "applied");

    // Retry names and retries only the failed change.
    fireEvent.click(screen.getByRole("button", { name: "Retry 1 change" }));
    expect(onRetry).toHaveBeenCalledWith(["c3"]);
  });

  test("computing shows what it is doing and keeps Apply disabled", () => {
    const { onApply } = renderPreview("computing");
    expect(screen.getByText("Comparing with each agent’s files…")).toBeInTheDocument();
    const apply = screen.getByRole("button", { name: "Apply" });
    expect(apply).toBeDisabled();
    fireEvent.click(apply);
    expect(onApply).not.toHaveBeenCalled();
  });

  test("empty says there is nothing to change and offers only Done", () => {
    const { onOpenChange } = renderPreview("empty", { items: [] });
    expect(screen.getByText("Nothing to change")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Apply/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("applying goes one target at a time and cannot be dismissed", () => {
    const items: ChangeItem[] = ITEMS.map((item, i) => ({
      ...item,
      status: i < 2 ? "applied" : i === 2 ? "applying" : "pending",
    }));
    const { onOpenChange } = renderPreview("applying", { items });
    expect(screen.getByText("Applying changes")).toBeInTheDocument();
    expect(screen.getByText("Applying 3 of 4…")).toBeInTheDocument();
    expect(within(rowOf("~/.claude.json")).getByRole("img", { name: "Applied" })).toBeTruthy();
    expect(
      within(rowOf("~/.codex/config.toml")).getByRole("img", { name: "Applying" }),
    ).toBeTruthy();
    expect(
      within(rowOf("~/.codex/skills/release-notes")).getByRole("img", { name: "Waiting" }),
    ).toBeTruthy();

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: "Close" })).toBeNull();
    fireEvent.keyDown(dialog, { key: "Escape" });
    fireEvent.pointerDown(document.body);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apply 4 changes" })).toBeDisabled();
  });

  test("applied records the write and links to Activity without a toast", () => {
    const { onOpenChange } = renderPreview("applied", { activityHref: "/activity" });
    expect(screen.getByText("Applied 4 changes")).toBeInTheDocument();
    expect(screen.getByText("Recorded in Activity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View in Activity" })).toHaveAttribute(
      "href",
      "/activity",
    );
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("handles any number of agents", () => {
    renderPreview("ready", {
      items: [
        ...ITEMS,
        { id: "c5", agentType: "codex", agentName: "Codex (work)", path: "~/w.toml", op: "add" },
      ],
    });
    expect(screen.getByTestId("changes-heading")).toHaveTextContent("Changes · 5");
    expect(screen.getByRole("region", { name: "Codex (work)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply 5 changes" })).toBeInTheDocument();
  });
  test("a caller can name the confirm, tint it destructive and replace the review note", () => {
    const { onApply } = renderPreview("ready", {
      applyLabel: "Disconnect",
      applyDestructive: true,
      note: "Only Coffer’s own lines are removed.",
    });
    expect(screen.getByText("Only Coffer’s own lines are removed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });
});
