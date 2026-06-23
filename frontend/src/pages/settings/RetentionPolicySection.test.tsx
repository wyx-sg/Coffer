// frontend/src/pages/settings/RetentionPolicySection.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RetentionPolicySection } from "./RetentionPolicySection";
import type { components } from "@/lib/api/types";

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
    expect(screen.getByText("Audit log")).toBeInTheDocument();
    // The description is provided via i18n (translated value shown in UI)
    expect(screen.getByText("Resource lifecycle events.")).toBeInTheDocument();
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
});
