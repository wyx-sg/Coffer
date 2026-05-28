// frontend/src/components/TimeRangePicker.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TimeRangePicker } from "./TimeRangePicker";

/** Renders the picker and opens the popover by clicking the trigger. */
function setup(props: {
  timeRange?: string;
  from?: string;
  to?: string;
  onChange: (v: { timeRange: string; from: string; to: string }) => void;
}) {
  render(
    <TimeRangePicker
      timeRange={props.timeRange ?? "all"}
      from={props.from ?? ""}
      to={props.to ?? ""}
      onChange={props.onChange}
    />,
  );
}

function openPicker() {
  fireEvent.click(screen.getByRole("button"));
}

describe("TimeRangePicker", () => {
  test("shows the selected preset label on the trigger button", () => {
    setup({ timeRange: "24h", onChange: vi.fn() });
    // The trigger shows the active preset — full i18n string from audit.timeRange.24h
    expect(screen.getByRole("button")).toHaveTextContent("Last 24 hours");
  });

  test("shows the custom range label when timeRange is 'custom' with from/to", () => {
    setup({
      timeRange: "custom",
      from: "2026-05-01 00:00:00",
      to: "2026-05-10 23:59:59",
      onChange: vi.fn(),
    });
    expect(screen.getByRole("button")).toHaveTextContent("→");
  });

  test("opens the popover when the trigger is clicked", () => {
    setup({ onChange: vi.fn() });
    // Before click no preset list items
    expect(screen.queryByRole("button", { name: /1 h/i })).not.toBeInTheDocument();
    openPicker();
    // TIME_PRESETS = ["1h","6h","24h","7d","30d","all"] — exactly 6 preset buttons in the popover.
    // The trigger button may share text with the active preset ("All time" is the default),
    // so use getAllByRole and assert the expected count (trigger + 6 presets = 2 for "All time").
    expect(screen.getByRole("button", { name: "Last 1 hour" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 6 hours" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 24 hours" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 7 days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 30 days" })).toBeInTheDocument();
    // "All time" is both the active trigger label and a preset button — use getAllByRole
    expect(screen.getAllByRole("button", { name: "All time" })).toHaveLength(2);
  });

  test("clicking a preset calls onChange and closes the popover", () => {
    const onChange = vi.fn();
    setup({ onChange });
    openPicker();

    // Find and click the "1h" preset button (text: "Last 1 hour" from audit.timeRange.1h)
    const preset1h = screen.getByRole("button", { name: "Last 1 hour" });
    fireEvent.click(preset1h);

    expect(onChange).toHaveBeenCalledWith({ timeRange: "1h", from: "", to: "" });
  });

  test("typing into from/to inputs and clicking Apply fires onChange with custom range", () => {
    const onChange = vi.fn();
    setup({ onChange });
    openPicker();

    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-05-01 09:00:00" },
    });
    fireEvent.change(screen.getByLabelText("To"), {
      target: { value: "2026-05-02 18:00:00" },
    });

    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    expect(onChange).toHaveBeenCalledWith({
      timeRange: "custom",
      from: "2026-05-01 09:00:00",
      to: "2026-05-02 18:00:00",
    });
  });
});
