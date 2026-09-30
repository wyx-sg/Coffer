// frontend/src/pages/settings/RetentionPolicySection.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { RetentionPolicySection } from "./RetentionPolicySection";
import type { components } from "@/lib/api/types";

// The shortening dialog counts what it would delete; each test sets the answer.
const preview = vi.hoisted(() => ({
  data: undefined as { total_rows: number; rows_to_delete: number } | undefined,
}));
vi.mock("@/lib/hooks/useRetention", () => ({
  useRetentionPreview: () => ({ data: preview.data }),
}));

type RetentionPolicyOut = components["schemas"]["RetentionPolicyOut"];

const basePolicy: RetentionPolicyOut = {
  table_name: "audit_log",
  display_name: "Audit log",
  description: "Tracks every lifecycle event.",
  default_retention_days: 90,
  retention_days: 30,
  last_pruned_at: null,
  last_pruned_rows: 0,
};

const foreverPolicy: RetentionPolicyOut = {
  table_name: "mcp_invocations",
  display_name: "MCP Invocations",
  description: "Tool call history.",
  default_retention_days: 30,
  retention_days: null,
  last_pruned_at: "2026-05-01T00:00:00Z",
  last_pruned_rows: 100,
};

describe("RetentionPolicySection", () => {
  test("renders the policy display name and description", () => {
    render(<RetentionPolicySection policy={basePolicy} onUpdate={vi.fn()} updating={false} />);
    expect(screen.getByText("Changes")).toBeInTheDocument();
    // The description is provided via i18n (translated value shown in UI)
    expect(
      screen.getByText("Every change made in Coffer, by you, the CLI, sync or an agent"),
    ).toBeInTheDocument();
  });

  test("shows the days input with the current retention value", () => {
    render(<RetentionPolicySection policy={basePolicy} onUpdate={vi.fn()} updating={false} />);
    const daysInput = screen.getByRole("spinbutton") as HTMLInputElement;
    expect(Number(daysInput.value)).toBe(30);
  });

  test("'keep forever' toggle is checked when retention_days is null", () => {
    render(<RetentionPolicySection policy={foreverPolicy} onUpdate={vi.fn()} updating={false} />);
    const toggle = screen.getByRole("switch") as HTMLInputElement;
    expect(toggle).toBeChecked();
    // Days input is hidden
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  test("toggling 'keep forever' on hides the days input", () => {
    render(<RetentionPolicySection policy={basePolicy} onUpdate={vi.fn()} updating={false} />);
    expect(screen.getByRole("spinbutton")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch"));
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  test("auto-saves (no Save button) — edits persist on change/blur", () => {
    render(<RetentionPolicySection policy={basePolicy} onUpdate={vi.fn()} updating={false} />);
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });

  test("toggling 'keep forever' on auto-saves onUpdate(null)", () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={basePolicy} onUpdate={onUpdate} updating={false} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(onUpdate).toHaveBeenCalledWith(null);
  });

  test("editing days and blurring auto-saves onUpdate(days)", () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={basePolicy} onUpdate={onUpdate} updating={false} />);
    const daysInput = screen.getByRole("spinbutton");
    fireEvent.change(daysInput, { target: { value: "60" } });
    fireEvent.blur(daysInput);
    expect(onUpdate).toHaveBeenCalledWith(60);
  });

  test("does not auto-save on blur when the days value is unchanged", () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={basePolicy} onUpdate={onUpdate} updating={false} />);
    fireEvent.blur(screen.getByRole("spinbutton"));
    expect(onUpdate).not.toHaveBeenCalled();
  });

  test("clamps an over-max days value to 3650 instead of sending it raw", () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={basePolicy} onUpdate={onUpdate} updating={false} />);
    const daysInput = screen.getByRole("spinbutton") as HTMLInputElement;
    fireEvent.change(daysInput, { target: { value: "99999" } });
    expect(Number(daysInput.value)).toBe(3650);
    fireEvent.blur(daysInput);
    expect(onUpdate).toHaveBeenCalledWith(3650);
  });

  test("a value under 1 is raised to 1 and says so", () => {
    render(<RetentionPolicySection policy={basePolicy} onUpdate={vi.fn()} updating={false} />);
    const daysInput = screen.getByRole("spinbutton") as HTMLInputElement;
    fireEvent.change(daysInput, { target: { value: "0" } });
    expect(Number(daysInput.value)).toBe(1);
    expect(screen.getByRole("status")).toHaveTextContent("Minimum is 1 day");

    fireEvent.change(daysInput, { target: { value: "45" } });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("shortening the window asks first, then saves on confirm", async () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={basePolicy} onUpdate={onUpdate} updating={false} />);
    const daysInput = screen.getByRole("spinbutton");
    fireEvent.change(daysInput, { target: { value: "7" } });
    fireEvent.blur(daysInput);
    expect(onUpdate).not.toHaveBeenCalled();

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Keep changes for 7 days?");
    fireEvent.click(within(dialog).getByRole("button", { name: "Shorten to 7 days" }));
    expect(onUpdate).toHaveBeenCalledWith(7);
  });

  test("the shortening names how many records it deletes, now and after", async () => {
    preview.data = { total_rows: 11210, rows_to_delete: 9400 };
    render(
      <RetentionPolicySection
        policy={{ ...basePolicy, table_name: "mcp_invocations" }}
        onUpdate={vi.fn()}
        updating={false}
      />,
    );
    const daysInput = screen.getByRole("spinbutton");
    fireEvent.change(daysInput, { target: { value: "7" } });
    fireEvent.blur(daysInput);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Keep MCP calls for 7 days?");
    expect(dialog).toHaveTextContent(
      "About 9,400 calls older than 7 days are deleted at the next cleanup, within six hours.",
    );
    expect(within(dialog).getByTestId("retention-shorten-now")).toHaveTextContent(
      "30 days · 11,210 calls",
    );
    expect(within(dialog).getByTestId("retention-shorten-after")).toHaveTextContent(
      "7 days · about 1,810 calls",
    );
    preview.data = undefined;
  });

  test("cancelling the shortening puts the field back", async () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={basePolicy} onUpdate={onUpdate} updating={false} />);
    const daysInput = screen.getByRole("spinbutton") as HTMLInputElement;
    fireEvent.change(daysInput, { target: { value: "7" } });
    fireEvent.blur(daysInput);

    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(onUpdate).not.toHaveBeenCalled();
    expect(Number(daysInput.value)).toBe(30);
  });

  test("turning keep-forever off is a shortening too, so it asks", async () => {
    const onUpdate = vi.fn();
    render(<RetentionPolicySection policy={foreverPolicy} onUpdate={onUpdate} updating={false} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(onUpdate).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /shorten/i }));
    expect(onUpdate).toHaveBeenCalledWith(30);
  });
});
