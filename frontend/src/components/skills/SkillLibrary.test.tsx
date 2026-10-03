// src/components/skills/SkillLibrary.test.tsx — the Skills library column, laid out like the MCP servers list: groups, filter rows, hover checkboxes and the selection bar at the top.
import { useState } from "react";
import { describe, expect, test, vi } from "vitest";
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
  test("groups In use, Unused, then Built-in with a count each", () => {
    renderLibrary();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["In use1", "Unused2", "Built-in1"]);
    expect(names(group("In use")!)[0]).toContain("alpha");
    expect(names(group("Unused")!).join()).toMatch(/beta.*gamma|gamma.*beta/);
    expect(names(group("Built-in")!)[0]).toContain("coffer-guide");
    expect(within(group("Built-in")!).getByTestId("skill-builtin-badge")).toBeInTheDocument();
  });

  test("there is no Kind filter; search and Reach apply to built-ins too", () => {
    renderLibrary();
    expect(screen.queryByRole("combobox", { name: "Kind" })).toBeNull();
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

  test("the built-in row has no checkbox; select-all skips it", () => {
    renderLibrary();
    expect(screen.queryByRole("checkbox", { name: /coffer-guide/ })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /Select row: alpha/ }));
    const bar = screen.getByRole("region", { name: "Selected skills" });
    expect(screen.queryByRole("textbox", { name: "Filter skills" })).toBeNull();
    const all = within(bar).getByRole("checkbox", {
      name: "Select all shown skills",
    }) as HTMLInputElement;
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(within(bar).getByText("3 selected")).toBeInTheDocument();
    expect(all.checked).toBe(true);
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
