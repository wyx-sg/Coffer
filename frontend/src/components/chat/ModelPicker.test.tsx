import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { ModelPicker } from "./ModelPicker";

vi.mock("@/lib/hooks/useAgentModels", () => ({ useAgentModels: vi.fn() }));
// Mocked though the component no longer reads it — see the guard test below.
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));

import type { AgentModel } from "@/lib/api/agentModels";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";

const useAgentModelsMock = useAgentModels as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;

/** The daemon-served catalogue per agent, read back from the installed agent
 * (`fable` is the case no frontend constant could have known about). */
const CATALOGUE: Record<string, AgentModel[]> = {
  // Claude Code names tier aliases and no model of its takes a reasoning effort;
  // Codex names concrete models and every one of its does.
  claude_code: [
    { id: "opus", label: "Opus", description: "", efforts: [], default_effort: null },
    { id: "sonnet", label: "Sonnet", description: "", efforts: [], default_effort: null },
    { id: "fable", label: "", description: "", efforts: [], default_effort: null },
  ],
  codex: [
    {
      id: "gpt-5-codex",
      label: "",
      description: "",
      efforts: ["low", "medium", "high", "xhigh"],
      default_effort: "xhigh",
    },
    {
      id: "gpt-5",
      label: "",
      description: "",
      efforts: ["low", "medium", "high"],
      default_effort: "medium",
    },
  ],
};

/** Open the Radix Select trigger and return its rendered option labels.
 *
 * jsdom has no PointerEvent, so drive the trigger via the keyboard (Radix opens
 * the listbox on ArrowDown / Enter / Space) rather than a pointer gesture. */
function openAndReadOptions(): string[] {
  const trigger = screen.getByRole("combobox", { name: /agent model/i });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  useListMock.mockReturnValue({ mutate: vi.fn() });
  useAgentModelsMock.mockImplementation((agentKey: string) => ({
    data: CATALOGUE[agentKey] ?? [],
  }));
});

describe("ModelPicker", () => {
  acceptance(
    "provider-switching",
    "the agent's model picker offers a fixed list without free-form entry",
    () => {
      // (A) The agent on its own login → its own catalogue, no "Custom…"
      // escape hatch, and no free-text input anywhere.
      const codex = render(<ModelPicker agentKey="codex" value={null} onCommit={vi.fn()} />);
      let options = openAndReadOptions();
      expect(options).toContain("gpt-5-codex");
      expect(options.some((o) => /custom/i.test(o))).toBe(false);
      expect(screen.queryByRole("textbox")).toBeNull();
      codex.unmount();

      // (B) A connection is active → the daemon answers with its curated ids,
      // and the list is still fixed. The picker does not decide this and never
      // did know the connection's stored model/fast_model.
      useAgentModelsMock.mockImplementation(() => ({
        data: [
          { id: "claude-sonnet-4-6", label: "", description: "", efforts: [], default_effort: null },
          { id: "claude-3-5-haiku", label: "", description: "", efforts: [], default_effort: null },
        ],
      }));
      render(<ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />);
      options = openAndReadOptions();
      expect(options).toContain("claude-sonnet-4-6");
      expect(options).toContain("claude-3-5-haiku");
      expect(options).not.toContain("claude-opus-4-8");
      expect(options.some((o) => /custom/i.test(o))).toBe(false);
    },
  );

  test("the daemon's answer IS the list — nothing is merged into it here", () => {
    // `/agent-providers/{key}/models` serves `offered()`: with a connection
    // active for this agent, its curated ids ARE the list, because the turns go
    // to that endpoint and not to the account the agent's own catalogue
    // describes. The picker used to fetch the endpoint itself and union the two,
    // so it offered ids the endpoint would reject — and disagreed with the
    // `/model` card in a chat, which has always read the same `offered()`.
    useAgentModelsMock.mockImplementation(() => ({
      data: [{ id: "gw/big", label: "", description: "", efforts: [], default_effort: null }],
    }));
    // Resolving with the agent's own ids, so a picker that still introspected
    // would visibly merge them back in.
    const mutate = vi.fn((_probe, opts) =>
      opts.onSuccess({ models: [{ id: "opus", modality: "text" }], message: "" }),
    );
    useListMock.mockReturnValue({ mutate });

    render(<ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />);
    const options = openAndReadOptions();

    expect(options).toContain("gw/big");
    expect(options.some((o) => o.includes("opus"))).toBe(false);
    expect(options.some((o) => o.includes("sonnet"))).toBe(false);
    expect(mutate).not.toHaveBeenCalled();
  });

  test("selecting a model the daemon offered commits it", () => {
    const onCommit = vi.fn();
    useAgentModelsMock.mockImplementation(() => ({
      data: [
        { id: "claude-sonnet-4-6", label: "", description: "", efforts: [], default_effort: null },
      ],
    }));
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: "claude-sonnet-4-6" }));
    expect(onCommit).toHaveBeenCalledWith("claude-sonnet-4-6");
  });

  test("a catalogue-only model such as fable is selectable", () => {
    // `fable` exists only in the daemon's answer — no frontend constant knows it.
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    expect(openAndReadOptions()).toContain("fable");
    fireEvent.click(screen.getByRole("option", { name: "fable" }));
    expect(onCommit).toHaveBeenCalledWith("fable");
  });

  test("an option leads with the display name, keeping the id as secondary text", () => {
    // The VALUE committed must be the bare id — it is passed verbatim to the CLI.
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    const options = openAndReadOptions();
    expect(options).toContain("Opusopus"); // label + id, rendered as one row
    fireEvent.click(screen.getByRole("option", { name: /^Opus\s*opus$/ }));
    expect(onCommit).toHaveBeenCalledWith("opus");
  });

  test("with no active connection, lists the agent's catalogue models and commits one", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="codex" value={null} onCommit={onCommit} />);
    const options = openAndReadOptions();
    expect(options).toContain("gpt-5-codex");
    fireEvent.click(screen.getByRole("option", { name: "gpt-5-codex" }));
    expect(onCommit).toHaveBeenCalledWith("gpt-5-codex");
  });

  acceptance("chat", "the model picker always offers the current value", () => {
    // codex agent, no openai override; the bound value is a one-off id.
    render(<ModelPicker agentKey="codex" value="my-finetune" onCommit={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: /agent model/i });
    expect(trigger).toHaveTextContent("my-finetune");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toContain("my-finetune");
    // The Default option leads, followed by the catalogue's models.
    expect(options).toEqual(["Default", "gpt-5-codex", "gpt-5", "my-finetune"]);
  });

  test("choosing Default commits null (inherit the projected default)", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="codex" value="my-finetune" onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: /default/i }));
    expect(onCommit).toHaveBeenCalledWith(null);
  });
});
