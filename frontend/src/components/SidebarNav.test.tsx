// frontend/src/components/SidebarNav.test.tsx
// The sidebar's information architecture, which is a product decision and not
// a styling one: what is a vault RESOURCE and what is something you DO.
//
// Resources claims to list one entry per resource kind that has a list UI, so
// that claim is what this pins down — a kind that grows a surface and never
// reaches the rail is reachable only by typing its URL, and a row that outlives
// its feature leads to a 404.
import { describe, expect, test } from "vitest";
import { render, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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
  test("Resources lists one entry per resource kind that has a list UI", () => {
    renderNav();

    expect(group("Resources").map(([name]) => name)).toEqual([
      "MCP servers",
      "Skills",
      "Knowledge",
      "Memory",
      "Model providers",
      "Channels",
    ]);
  });

  test("Agents holds what you DO with an agent, not vault assets", () => {
    renderNav();

    expect(group("Agents")).toEqual([
      ["Agents", "/agents"],
      ["Chat", "/chat"],
    ]);
  });
});
