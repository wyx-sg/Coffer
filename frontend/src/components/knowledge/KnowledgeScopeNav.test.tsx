// frontend/src/components/knowledge/KnowledgeScopeNav.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { KnowledgeScopeNav } from "./KnowledgeScopeNav";
import { WORKSPACE_GLOBAL_PROJECT_ID, type KnowledgeScope } from "@/lib/api/knowledge";

const SCOPES: KnowledgeScope[] = [
  {
    id: WORKSPACE_GLOBAL_PROJECT_ID,
    kind: "global",
    label: "",
    projectRoot: null,
    memoryStoreName: "global",
  },
  {
    id: "PULID",
    kind: "project",
    label: "coffer",
    projectRoot: "/Users/me/code/coffer",
    memoryStoreName: "project-x",
  },
];

describe("KnowledgeScopeNav", () => {
  test("renders Global plus each project by readable name + path", () => {
    render(<KnowledgeScopeNav scopes={SCOPES} selectedId={undefined} onSelect={() => {}} />);
    expect(screen.getByText("Global")).toBeInTheDocument();
    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("/Users/me/code/coffer")).toBeInTheDocument();
  });

  test("marks the selected scope with aria-current", () => {
    render(<KnowledgeScopeNav scopes={SCOPES} selectedId="PULID" onSelect={() => {}} />);
    const projectBtn = screen.getByText("coffer").closest("button");
    expect(projectBtn).toHaveAttribute("aria-current", "true");
  });

  test("fires onSelect with the chosen scope", () => {
    const onSelect = vi.fn();
    render(<KnowledgeScopeNav scopes={SCOPES} selectedId={undefined} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("coffer"));
    expect(onSelect).toHaveBeenCalledWith(SCOPES[1]);
  });
});
