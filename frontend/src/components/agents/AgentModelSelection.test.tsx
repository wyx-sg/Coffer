// The curation screen. Its whole reason to exist is that the catalogue an agent
// reports names models the account may not be entitled to run, and nothing on
// this machine can tell which — so the user is the authority and these tests pin
// the two rules that makes: nothing ticked means EVERYTHING is offered, and the
// catalogue itself is never narrowed by what is ticked.
import { beforeEach, describe, expect, test, vi } from "vitest";

import { fireEvent, render, screen } from "@testing-library/react";

import { AgentModelSelection } from "./AgentModelSelection";
import type { AgentModel } from "@/lib/api/agentModels";

vi.mock("@/lib/hooks/useAgentModels", () => ({
  useAgentModels: vi.fn(),
  useAgentModelSelection: vi.fn(),
  useSetAgentModelSelection: vi.fn(),
}));

import {
  useAgentModels,
  useAgentModelSelection,
  useSetAgentModelSelection,
} from "@/lib/hooks/useAgentModels";

const catalogueMock = useAgentModels as unknown as ReturnType<typeof vi.fn>;
const selectionMock = useAgentModelSelection as unknown as ReturnType<typeof vi.fn>;
const saveMock = useSetAgentModelSelection as unknown as ReturnType<typeof vi.fn>;
const mutate = vi.fn();

const CATALOGUE: AgentModel[] = [
  { id: "claude-opus-5", label: "Opus 5", description: "" },
  { id: "claude-mythos-5", label: "Mythos 5", description: "" },
  { id: "claude-haiku-4-5", label: "Haiku 4.5", description: "" },
];

const saveButton = () => screen.getByRole("button", { name: /save|保存/i });
const box = (id: string) => screen.getByRole("checkbox", { name: id }) as HTMLInputElement;

beforeEach(() => {
  vi.clearAllMocks();
  catalogueMock.mockReturnValue({ data: CATALOGUE, isLoading: false });
  selectionMock.mockReturnValue({ data: [], isLoading: false });
  saveMock.mockReturnValue({ mutate, isPending: false, isError: false });
});

describe("AgentModelSelection", () => {
  test("an uncurated agent shows every model, none ticked", () => {
    render(<AgentModelSelection agentType="claude_code" />);

    for (const m of CATALOGUE) expect(box(m.id).checked).toBe(false);
    // The out-of-the-box state must READ as "all of them", not as "none".
    expect(screen.getByText(/all 3 models are offered/i)).toBeInTheDocument();
  });

  test("the catalogue shows unticked models too", () => {
    // If curation narrowed the catalogue, a model could be un-ticked once and
    // never ticked back on.
    selectionMock.mockReturnValue({ data: ["claude-opus-5"], isLoading: false });
    render(<AgentModelSelection agentType="claude_code" />);

    expect(box("claude-opus-5").checked).toBe(true);
    expect(box("claude-mythos-5").checked).toBe(false);
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  test("ticking is a draft until it is saved", () => {
    render(<AgentModelSelection agentType="claude_code" />);
    expect(saveButton()).toBeDisabled();

    fireEvent.click(box("claude-opus-5"));
    fireEvent.click(box("claude-haiku-4-5"));

    // Eleven ticks should be one write, not eleven.
    expect(mutate).not.toHaveBeenCalled();
    expect(saveButton()).toBeEnabled();

    fireEvent.click(saveButton());
    expect(mutate).toHaveBeenCalledWith(["claude-opus-5", "claude-haiku-4-5"]);
  });

  test("un-ticking everything saves the empty set, which restores the catalogue", () => {
    selectionMock.mockReturnValue({ data: ["claude-opus-5"], isLoading: false });
    render(<AgentModelSelection agentType="claude_code" />);

    fireEvent.click(box("claude-opus-5"));
    fireEvent.click(saveButton());

    // `[]` is "not curated", never "offer nothing".
    expect(mutate).toHaveBeenCalledWith([]);
  });

  test("an agent whose CLI reports nothing says so instead of an empty list", () => {
    catalogueMock.mockReturnValue({ data: [], isLoading: false });
    render(<AgentModelSelection agentType="codex" />);

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/no model catalogue|暂无可用的模型清单/i)).toBeInTheDocument();
  });

  test("a failed save is reported rather than silently swallowed", () => {
    saveMock.mockReturnValue({ mutate, isPending: false, isError: true });
    render(<AgentModelSelection agentType="claude_code" />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
