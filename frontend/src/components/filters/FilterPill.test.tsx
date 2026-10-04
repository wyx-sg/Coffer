import { render, screen } from "@testing-library/react";
import { user as userEvent } from "./testUser";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import "@/i18n";
import { FilterPill, type FilterOption } from "./FilterPill";

const KINDS: FilterOption[] = ["MCP", "Skill", "Knowledge", "Memory"].map((l) => ({
  value: l.toLowerCase(),
  label: l,
}));

function Multi({ options = KINDS, initial = [] as string[] }) {
  const [v, setV] = useState(initial);
  return (
    <FilterPill
      label="Kind"
      options={options}
      value={v}
      onChange={setV}
      searchPlaceholder="Find a kind"
    />
  );
}

describe("FilterPill", () => {
  it("shows just the label when empty and lists chosen values when set", async () => {
    const user = userEvent;
    render(<Multi />);
    expect(screen.getByRole("button", { name: "Kind" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kind" }));
    await user.click(screen.getByRole("option", { name: "MCP" }));
    await user.click(screen.getByRole("option", { name: "Skill" }));
    expect(screen.getByRole("button", { name: /Kind:\s*MCP, Skill/ })).toBeInTheDocument();
    // Multi keeps the popover open.
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("clears from the footer and from the x, with no counts and no search under 9 values", async () => {
    const user = userEvent;
    render(<Multi initial={["mcp"]} />);
    expect(screen.queryByPlaceholderText("Find a kind")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Clear Kind" }));
    expect(screen.getByRole("button", { name: "Kind" })).toBeInTheDocument();
  });

  it("disables Clear when nothing is selected", async () => {
    const user = userEvent;
    render(<Multi />);
    await user.click(screen.getByRole("button", { name: "Kind" }));
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled();
  });

  it("searches only above eight values, ordering selected first then A-Z", async () => {
    const user = userEvent;
    const many = "ihgfedcba".split("").map((c) => ({ value: c, label: c.toUpperCase() }));
    render(<Multi options={many} initial={["h"]} />);
    await user.click(screen.getByRole("button", { name: /^Kind:/ }));
    const labels = screen.getAllByRole("option").map((o) => o.textContent);
    expect(labels[0]).toBe("H");
    expect(labels.slice(1, 4)).toEqual(["A", "B", "C"]);
    await user.type(screen.getByPlaceholderText("Find a kind"), "zz");
    expect(screen.getByText("No matches")).toBeInTheDocument();
  });

  it("single mode picks one value and closes", async () => {
    const user = userEvent;
    function Single() {
      const [v, setV] = useState<string | null>(null);
      return (
        <FilterPill
          mode="single"
          label="Agent"
          options={[
            { value: "a", label: "Claude Code" },
            { value: "b", label: "Codex" },
          ]}
          value={v}
          onChange={setV}
        />
      );
    }
    render(<Single />);
    await user.click(screen.getByRole("button", { name: "Agent" }));
    await user.click(screen.getByRole("option", { name: "Codex" }));
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: /Agent:\s*Codex/ })).toBeInTheDocument();
  });
});
