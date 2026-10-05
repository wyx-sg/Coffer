// src/components/skills/SkillLibrary.test.tsx — the Skills library column, laid out like the MCP servers list: groups, filter rows, hover checkboxes and the selection bar at the top.
import { useState } from "react";
import { describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { SkillOut } from "@/lib/api/skills";
import { BUILTIN_SKILL, makeSkill } from "@/test/skillsPageKit";
import { SkillLibrary } from "./SkillLibrary";

vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));
vi.mock("@/lib/hooks/useClis", () => ({ useClis: () => ({ data: { items: [] } }) }));
vi.mock("./SkillOrphanList", () => ({ SkillOrphanList: () => null }));

const SKILLS: SkillOut[] = [
  BUILTIN_SKILL,
  makeSkill({ uid: "u-bad", name: "delta", master_missing: true }),
  makeSkill({ uid: "u-on", name: "alpha" }),
  makeSkill({ uid: "u-off", name: "beta", enabled: false }),
  makeSkill({ uid: "u-none", name: "gamma", scope: { agents: [] } }),
];

function Harness({ skills = SKILLS }: { skills?: SkillOut[] }) {
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  return (
    <SkillLibrary
      skills={skills}
      isLoading={false}
      selectedName={null}
      hrefFor={(n) => `/skills/${n}`}
      onOpenSkill={() => {}}
      onCheckCopies={() => {}}
      checkingCopies={false}
      drift={undefined}
      picked={picked}
      onPickedChange={setPicked}
      selected={skills.filter((s) => !s.builtin && picked.has(s.uid))}
      orphan={null}
    />
  );
}

function renderLibrary(skills?: SkillOut[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter>
            <Harness skills={skills} />
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const group = (name: string) => screen.queryByRole("region", { name });
const names = (el: HTMLElement) =>
  within(el)
    .getAllByRole("link")
    .map((a) => a.textContent);

describe("SkillLibrary", () => {
  test("groups Needs attention, In use, Off, then Built-in, no count on the titles", () => {
    renderLibrary();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Needs attention", "In use", "Off", "Built-in"]);
    expect(names(group("Needs attention")!)[0]).toContain("delta");
    expect(names(group("Needs attention")!)[0]).toContain("Master missing");
    expect(names(group("In use")!)[0]).toContain("alpha");
    expect(names(group("Off")!).join()).toMatch(/beta.*gamma|gamma.*beta/);
    expect(names(group("Built-in")!)[0]).toContain("coffer-guide");
    expect(within(group("Built-in")!).getByTestId("skill-builtin-badge")).toBeInTheDocument();
  });

  test("a row shows no description, and Off rows carry no reach word", () => {
    renderLibrary();
    expect(within(group("In use")!).queryByText("Say hello nicely.")).toBeNull();
    expect(names(group("Off")!).every((n) => !n?.includes("Off"))).toBe(true);
  });

  test("the only filters are search and Reach; search applies to built-ins too", () => {
    renderLibrary();
    expect(screen.getAllByRole("combobox").map((c) => c.getAttribute("aria-label"))).toEqual([
      "Reach",
    ]);
    expect(screen.getByRole("button", { name: "Check copies" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter skills" }), {
      target: { value: "zzz" },
    });
    expect(screen.getByText("No skill matches “zzz”")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter skills" }), {
      target: { value: "guide" },
    });
    expect(group("Built-in")).not.toBeNull();
    expect(group("In use")).toBeNull();
  });

  test("a select-all row appears once a row is ticked and ticks every listed skill, not the built-in one", () => {
    renderLibrary();
    expect(screen.queryByRole("checkbox", { name: "Select all" })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: alpha/ }));
    const all = screen.getByRole("checkbox", { name: "Select all" }) as HTMLInputElement;
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(screen.getByText("4 of 4 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all" }));
    expect(screen.queryByRole("region", { name: "Selected skills" })).toBeNull();
  });

  test("the built-in row has no checkbox and the bar counts the others only", () => {
    renderLibrary();
    expect(screen.queryByRole("checkbox", { name: /coffer-guide/ })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: alpha/ }));
    const bar = screen.getByRole("region", { name: "Selected skills" });
    expect(screen.queryByRole("textbox", { name: "Filter skills" })).toBeNull();
    expect(within(bar).getByText("1 of 4 selected")).toBeInTheDocument();
    expect(within(bar).queryByRole("checkbox")).toBeNull();
    fireEvent.click(within(bar).getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("region", { name: "Selected skills" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Filter skills" })).toBeInTheDocument();
  });

  test("a row's checkbox shows on hover or focus only, and on every row once any is ticked", () => {
    renderLibrary();
    const slot = (name: RegExp) =>
      screen.getByRole("checkbox", { name }).parentElement?.parentElement as HTMLElement;
    expect(slot(/Select row: alpha/).className).toContain("hidden");
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: alpha/ }));
    expect(slot(/Select row: beta/).className).not.toContain("hidden");
  });
});

describe("SkillLibrary row click", () => {
  acceptance("web-ui", "a click anywhere on a list row opens its detail", () => {
    renderLibrary();
    const link = screen.getByRole("link", { name: /alpha/ });
    const opened = vi.fn((e: Event) => e.preventDefault());
    link.addEventListener("click", opened);
    const row = link.closest("li")!;
    fireEvent.click(row);
    expect(opened).toHaveBeenCalledTimes(1);
    // Cmd-click on the row and a click on its checkbox leave it alone.
    fireEvent.click(row, { metaKey: true });
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: alpha/ }));
    expect(opened).toHaveBeenCalledTimes(1);
  });
});
