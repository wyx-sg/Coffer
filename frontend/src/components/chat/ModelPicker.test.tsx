import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ModelPicker } from "./ModelPicker";

vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));

import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;

function makeProfile(over: Record<string, unknown> = {}) {
  return {
    name: "p1",
    wire_format: "anthropic",
    base_url: "https://api.example",
    credential_ref: "ref",
    model: "claude-opus-4-8",
    fast_model: "claude-haiku-4-5",
    wire_api: "chat",
    is_active: true,
    enabled: true,
    created_at: "",
    updated_at: "",
    ...over,
  };
}

function options(container: HTMLElement): (string | null)[] {
  return Array.from(container.querySelectorAll("option")).map((o) => o.getAttribute("value"));
}

beforeEach(() => {
  useProvidersMock.mockReturnValue({ data: [makeProfile()] });
  useListMock.mockReturnValue({ mutate: vi.fn() });
});

describe("ModelPicker", () => {
  test("suggests the active profile model + fast_model and shows the default hint", () => {
    const { container } = render(
      <ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />,
    );
    expect(options(container)).toEqual(["claude-opus-4-8", "claude-haiku-4-5"]);
    expect(screen.getByLabelText(/agent model/i)).toHaveAttribute(
      "placeholder",
      "Default: claude-opus-4-8",
    );
  });

  test("commits a trimmed value on blur", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value={null} onCommit={onCommit} />);
    const input = screen.getByLabelText(/agent model/i);
    fireEvent.change(input, { target: { value: "  custom-model  " } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith("custom-model");
  });

  test("clearing the text commits null (inherit the default)", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value="claude-opus-4-8" onCommit={onCommit} />);
    const input = screen.getByLabelText(/agent model/i);
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith(null);
  });

  test("does not commit when the value is unchanged", () => {
    const onCommit = vi.fn();
    render(<ModelPicker agentKey="claude_code" value="claude-opus-4-8" onCommit={onCommit} />);
    fireEvent.blur(screen.getByLabelText(/agent model/i));
    expect(onCommit).not.toHaveBeenCalled();
  });

  test("introspects once on first focus and merges fetched models (deduped)", () => {
    const mutate = vi.fn((_probe, opts) =>
      opts.onSuccess({ models: ["claude-sonnet-4-6", "claude-opus-4-8"], message: "" }),
    );
    useListMock.mockReturnValue({ mutate });
    const { container } = render(
      <ModelPicker agentKey="claude_code" value={null} onCommit={vi.fn()} />,
    );
    const input = screen.getByLabelText(/agent model/i);
    fireEvent.focus(input);
    fireEvent.focus(input); // second focus must not re-fetch
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(options(container)).toEqual([
      "claude-opus-4-8",
      "claude-haiku-4-5",
      "claude-sonnet-4-6",
    ]);
  });

  test("with no active profile for the agent's wire, offers no suggestions but allows free text", () => {
    // Only an anthropic profile is active; a codex (openai) agent has none.
    const onCommit = vi.fn();
    const { container } = render(<ModelPicker agentKey="codex" value={null} onCommit={onCommit} />);
    expect(options(container)).toEqual([]);
    const input = screen.getByLabelText(/agent model/i);
    fireEvent.change(input, { target: { value: "gpt-5-codex" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith("gpt-5-codex");
  });
});
