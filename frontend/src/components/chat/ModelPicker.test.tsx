import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ModelPicker } from "./ModelPicker";

vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));

import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;

function makeConnection(over: Record<string, unknown> = {}) {
  return {
    name: "p1",
    wire_format: "anthropic",
    base_url: "https://api.example",
    credential_ref: "ref",
    model: "claude-opus-4-8",
    fast_model: "claude-haiku-4-5",
    wire_api: "chat",
    is_active: true,
    internal_default: false,
    enabled: true,
    created_at: "",
    updated_at: "",
    ...over,
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

beforeEach(() => {
  vi.clearAllMocks();
  useProvidersMock.mockReturnValue({ data: [makeConnection()] });
  useListMock.mockReturnValue({ mutate: vi.fn() });
});

describe("ModelPicker", () => {
  test("renders a dropdown listing the active connection's model + fast_model", () => {
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />);
    const options = openAndReadOptions();
    expect(options).toContain("claude-opus-4-8");
    expect(options).toContain("claude-haiku-4-5");
    // A custom-entry escape hatch is always offered (model ids are free-form).
    expect(options.some((o) => /custom/i.test(o))).toBe(true);
  });

  test("selecting a listed model commits it", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: "claude-haiku-4-5" }));
    expect(onCommit).toHaveBeenCalledWith("claude-haiku-4-5");
  });

  test("choosing Custom… reveals a free-text input that commits any id on blur", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    openAndReadOptions();
    fireEvent.click(screen.getByRole("option", { name: /custom/i }));
    const input = screen.getByLabelText(/agent model/i);
    fireEvent.change(input, { target: { value: "  some-custom-id  " } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith("some-custom-id");
  });

  test("introspects on first open and merges fetched models (deduped)", () => {
    const mutate = vi.fn((_probe, opts) =>
      opts.onSuccess({ models: ["claude-sonnet-4-6", "claude-opus-4-8"], message: "" }),
    );
    useListMock.mockReturnValue({ mutate });
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: /agent model/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" }); // second open must not re-fetch
    expect(mutate).toHaveBeenCalledTimes(1);
    const options = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(options).toContain("claude-sonnet-4-6");
    // opus appears once (deduped against the connection's own model)
    expect(options.filter((o) => o === "claude-opus-4-8")).toHaveLength(1);
  });

  test("with no active connection, lists the agent's built-in models", () => {
    // Only an anthropic connection is active; a codex (openai) agent has no
    // override → it runs on its own login, so the picker offers codex's curated
    // built-in models (ADR-032 amendment D4) and selecting one commits it.
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="codex" value={null} onCommit={onCommit} />);
    const options = openAndReadOptions();
    expect(options).toContain("gpt-5-codex");
    fireEvent.click(screen.getByRole("option", { name: "gpt-5-codex" }));
    expect(onCommit).toHaveBeenCalledWith("gpt-5-codex");
  });

  test("a custom (non-listed) current value renders in the free-text input", () => {
    render(<ModelPicker agentKey="claude_code" value="my-finetune" onCommit={vi.fn()} />);
    // Not one of the connection's models → shown in the editable input directly.
    expect(screen.getByLabelText(/agent model/i)).toHaveValue("my-finetune");
  });

  test("clearing the free-text value commits null (inherit the default)", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value="my-finetune" onCommit={onCommit} />);
    const input = screen.getByLabelText(/agent model/i);
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith(null);
  });

  test("does not commit when the free-text value is unchanged", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value="my-finetune" onCommit={onCommit} />);
    fireEvent.blur(screen.getByLabelText(/agent model/i));
    expect(onCommit).not.toHaveBeenCalled();
  });
});
