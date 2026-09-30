// src/components/custom-tools/DraftReachField.test.tsx — a form's reach: a button over a panel that
// writes nothing itself, only hands the draft back.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { DraftReachField } from "./DraftReachField";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({
    data: [
      { uid: "ag-cc", name: "claude-code", type: "claude_code", state: "installed" },
      { uid: "ag-cx", name: "codex", type: "codex", state: "installed" },
    ],
  })),
}));

describe("DraftReachField", () => {
  test("narrowing ticks agents into the draft", () => {
    const onChange = vi.fn();
    render(<DraftReachField value={null} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Every agent" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "codex" }));
    expect(onChange).toHaveBeenCalledWith(["ag-cx"]);
  });

  test("pick-only counts the chosen agents against every agent", () => {
    const onChange = vi.fn();
    render(<DraftReachField value={["ag-cc"]} onChange={onChange} pickOnly />);
    fireEvent.click(screen.getByRole("button", { name: "1 of 2 agents" }));
    expect(screen.queryByRole("radio")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "claude-code" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
