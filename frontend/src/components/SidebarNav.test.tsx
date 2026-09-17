// frontend/src/components/SidebarNav.test.tsx
// The sidebar's information architecture, which is a product decision and not
// a styling one: what is a vault RESOURCE and what is something you DO.
//
// The case that made this worth a test is workflows. A template is a resource
// of kind `workflow`; a run of one is operational state that belongs to a
// single machine and never syncs. They had been built as one surface, reached
// through each other, which put a resource kind in the Agents group and left
// Resources one entry short of the kinds it claims to list one-to-one.
import { describe, expect, test } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarNav } from "./SidebarNav";

function renderNav(at = "/") {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <TooltipProvider>
        <SidebarNav collapsed={false} />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

/** The rows of the group whose label is `label`, as `[name, href]` pairs.
 *  Found by the group-label class rather than by text: "Agents" is both a
 *  group heading and a row inside it. */
function group(label: string): [string, string | null][] {
  const heading = Array.from(document.querySelectorAll(".nav-group-label")).find(
    (node) => node.textContent === label,
  );
  const container = heading!.parentElement!;
  return within(container)
    .getAllByRole("link")
    .map((link) => [link.textContent ?? "", link.getAttribute("href")]);
}

describe("SidebarNav", () => {
  acceptance(
    "workflow",
    "a template is found where the other resources are, and a run is not",
    () => {
      renderNav();

      const resources = group("Resources");
      const agents = group("Agents");

      // The workflow kind sits with the kinds…
      expect(resources).toContainEqual(["Workflows", "/workflows"]);
      // …and a run of one sits with the things you do with an agent.
      expect(agents).toContainEqual(["Runs", "/runs"]);

      // Neither is reachable only through the other: both are top-level rows.
      expect(agents.map(([name]) => name)).not.toContain("Workflows");
      expect(resources.map(([name]) => name)).not.toContain("Runs");
    },
  );

  test("Resources lists one entry per resource kind that has a list UI", () => {
    renderNav();

    expect(group("Resources").map(([name]) => name)).toEqual([
      "MCP servers",
      "Skills",
      "Knowledge",
      "Memory",
      "Model providers",
      "Channels",
      "Workflows",
    ]);
  });

  test("a run's own URL highlights Runs and leaves Workflows alone", () => {
    // Entries match by path prefix, so the two had to stop sharing one — on
    // `/workflows/small-change` the old layout lit up both rows at once.
    renderNav("/runs/run-1/nodes/write_td");

    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Workflows" })).not.toHaveAttribute("aria-current");
  });

  test("a workflow's own URL highlights Workflows and leaves Runs alone", () => {
    renderNav("/workflows/small-change");

    expect(screen.getByRole("link", { name: "Workflows" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Runs" })).not.toHaveAttribute("aria-current");
  });
});
