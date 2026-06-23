import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { ModelPicker } from "./ModelPicker";

vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));

import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;

function makeConnection(over: Record<string, unknown> = {}) {
  const merged = {
    name: "p1",
    protocol: "anthropic",
    base_url: "https://api.example",
    credential_ref: "ref",
    // The stored model/fast_model must NEVER feed the picker (D4 / E1).
    is_active: true,
    internal_default: false,
    enabled: true,
    created_at: "",
    updated_at: "",
    ...over,
  };
  // The picker matches the active connection by its compatible-agents set; default
  // it from the wire unless a test pins it explicitly.
  return {
    ...merged,
    compatible_agents:
      over.compatible_agents ?? (merged.protocol === "openai" ? ["codex"] : ["claude_code"]),
  };
}

/** Open the Radix Select trigger and return its rendered option labels.
 *
 * jsdom has no PointerEvent, so drive the trigger via the keyboard (Radix opens
 * the listbox on ArrowDown / Enter / Space) rather than a pointer gesture. */
function openAndReadOptions(): string[] {
  const trigger = screen.getByRole("combobox", { name: /agent model/i });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

/** mutate stub that resolves list-models introspection with the given ids. */
function introspectReturning(models: string[]) {
  return vi.fn((_probe, opts) => opts.onSuccess({ models, message: "" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  useProvidersMock.mockReturnValue({ data: [makeConnection()] });
  useListMock.mockReturnValue({ mutate: vi.fn() });
});

describe("ModelPicker", () => {
  acceptance(
    "011-provider-switching",
    "the chat model picker offers a fixed list without free-form entry",
    () => {
      // (A) No overriding connection for the agent → fixed built-in list, no
      // "Custom…" escape hatch, and no free-text input anywhere.
      const codex = render(<ModelPicker agentKey="codex" value={null} onCommit={vi.fn()} />);
      let options = openAndReadOptions();
      expect(options).toContain("gpt-5-codex");
      expect(options.some((o) => /custom/i.test(o))).toBe(false);
      expect(screen.queryByRole("textbox")).toBeNull();
      codex.unmount();

      // (B) A connection overrides the agent → the dropdown lists the
      // connection's INTROSPECTED models, never its stored `model`/`fast_model`.
      useListMock.mockReturnValue({
        mutate: introspectReturning(["claude-sonnet-4-6", "claude-3-5-haiku"]),
      });
      render(<ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />);
      options = openAndReadOptions();
      expect(options).toContain("claude-sonnet-4-6");
      expect(options).toContain("claude-3-5-haiku");
      // The stored connection model/fast_model are NOT offered.
      expect(options).not.toContain("claude-opus-4-8");
      expect(options.some((o) => /custom/i.test(o))).toBe(false);
    },
  );

  test("selecting a listed (introspected) model commits it", () => {
    const onCommit = vi.fn();
    useListMock.mockReturnValue({ mutate: introspectReturning(["claude-sonnet-4-6"]) });
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: "claude-sonnet-4-6" }));
    expect(onCommit).toHaveBeenCalledWith("claude-sonnet-4-6");
  });

  test("introspects on first open only (not on the second open)", () => {
    const mutate = introspectReturning(["claude-sonnet-4-6"]);
    useListMock.mockReturnValue({ mutate });
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: /agent model/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" }); // second open must not re-fetch
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toContain("claude-sonnet-4-6");
  });

  test("with no active connection, lists the agent's built-in models and commits one", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="codex" value={null} onCommit={onCommit} />);
    const options = openAndReadOptions();
    expect(options).toContain("gpt-5-codex");
    fireEvent.click(screen.getByRole("option", { name: "gpt-5-codex" }));
    expect(onCommit).toHaveBeenCalledWith("gpt-5-codex");
  });

  test("the current value is always selectable even when not in the source list", () => {
    // codex agent, no openai override; the bound value is a one-off id.
    render(<ModelPicker agentKey="codex" value="my-finetune" onCommit={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: /agent model/i });
    expect(trigger).toHaveTextContent("my-finetune");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toContain("my-finetune");
  });

  test("choosing Default commits null (inherit the projected default)", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="codex" value="my-finetune" onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: /default/i }));
    expect(onCommit).toHaveBeenCalledWith(null);
  });
});
