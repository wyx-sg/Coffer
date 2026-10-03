import { render, screen } from "@testing-library/react";
import { user as userEvent } from "./testUser";
import { describe, expect, it, vi } from "vitest";

import "@/i18n";
import { TimeRangePill } from "./TimeRangePill";

const PRESETS = [
  { id: "1h", label: "Last hour" },
  { id: "24h", label: "Last 24 h" },
];

describe("TimeRangePill", () => {
  it("shows the preset name and picks another preset", async () => {
    const onChange = vi.fn();
    render(<TimeRangePill value="24h" onChange={onChange} presets={PRESETS} />);
    await userEvent.click(screen.getByRole("button", { name: /Last 24 h/ }));
    await userEvent.click(screen.getByRole("option", { name: "Last hour" }));
    expect(onChange).toHaveBeenCalledWith("1h");
  });

  it("words a custom value on the pill", () => {
    render(<TimeRangePill value="2020-01-05T14:00..now" onChange={() => {}} presets={PRESETS} />);
    expect(screen.getByRole("button", { name: /Jan 5, 2020, 14:00 – now/ })).toBeInTheDocument();
  });

  it("has Apply disabled until a start day is picked and offers Cancel", async () => {
    render(<TimeRangePill value="24h" onChange={() => {}} presets={PRESETS} />);
    await userEvent.click(screen.getByRole("button", { name: /Last 24 h/ }));
    await userEvent.click(screen.getByRole("option", { name: "Custom range…" }));
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
  });

  it("hides the time fields in date-only mode", async () => {
    render(<TimeRangePill value="24h" onChange={() => {}} presets={PRESETS} dateOnly />);
    await userEvent.click(screen.getByRole("button", { name: /Last 24 h/ }));
    await userEvent.click(screen.getByRole("option", { name: "Custom range…" }));
    expect(screen.queryByLabelText(/HH:MM/)).toBeNull();
  });
});
