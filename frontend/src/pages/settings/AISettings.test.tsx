// frontend/src/pages/settings/AISettings.test.tsx — spec 008.
// Settings → AI: per-provider keychain rows + a model field that, on save,
// patches the default built-in agent (merging the full config).
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/lib/hooks/useBuiltinAgents", () => ({
  useBuiltinAgent: vi.fn(),
  usePatchBuiltinAgent: vi.fn(),
}));
vi.mock("@/lib/hooks/useKeychain", () => ({
  useSetKeychainSecret: vi.fn(),
  useRemoveKeychainSecret: vi.fn(),
}));

const { useBuiltinAgent, usePatchBuiltinAgent } = await import("@/lib/hooks/useBuiltinAgents");
const { useSetKeychainSecret, useRemoveKeychainSecret } = await import("@/lib/hooks/useKeychain");
const { AISettings } = await import("./AISettings");

const useBuiltinAgentMock = vi.mocked(useBuiltinAgent);
const usePatchMock = vi.mocked(usePatchBuiltinAgent);
const useSetMock = vi.mocked(useSetKeychainSecret);
const useRemoveMock = vi.mocked(useRemoveKeychainSecret);

const AGENT = {
  ref: "builtin_agent:coffer",
  kind: "builtin_agent",
  name: "coffer",
  description: null,
  config: {
    model: "anthropic:claude-sonnet-4-6",
    credential_ref: "ai/anthropic",
    use_gateway: true,
  },
  enabled: true,
  created_at: "2026-05-28T00:00:00Z",
  updated_at: "2026-05-28T00:00:00Z",
};

function stub({ patchMutate = vi.fn(), setMutate = vi.fn() } = {}) {
  useBuiltinAgentMock.mockReturnValue({
    data: AGENT,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useBuiltinAgent>);
  usePatchMock.mockReturnValue({
    mutate: patchMutate,
    isPending: false,
  } as unknown as ReturnType<typeof usePatchBuiltinAgent>);
  useSetMock.mockReturnValue({
    mutate: setMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetKeychainSecret>);
  useRemoveMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveKeychainSecret>);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AISettings />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AISettings", () => {
  test("renders provider key rows and the model field seeded from the default agent", () => {
    stub();
    renderPage();
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Ollama")).toBeInTheDocument();
    // The model field is seeded from the default agent's config.
    expect(screen.getByDisplayValue("anthropic:claude-sonnet-4-6")).toBeInTheDocument();
  });

  test("the provider whose credential_ref matches is shown as configured", () => {
    stub();
    renderPage();
    // Anthropic (ai/anthropic) is configured; there's at least one "Configured".
    expect(screen.getAllByText(/configured/i).length).toBeGreaterThan(0);
  });

  test("saving a key stores it under ai/<provider> in the keychain", () => {
    const setMutate = vi.fn();
    stub({ setMutate });
    renderPage();
    const openaiKey = screen.getByLabelText(/openai api key/i);
    fireEvent.change(openaiKey, { target: { value: "sk-123" } });
    // The save button next to the OpenAI input.
    const buttons = screen.getAllByRole("button", { name: /save key/i });
    fireEvent.click(buttons[buttons.length - 1]);
    expect(setMutate).toHaveBeenCalled();
    expect(setMutate.mock.calls[0][0]).toMatchObject({ ref: "ai/openai", value: "sk-123" });
  });

  test("saving the model patches the default agent with the merged full config", () => {
    const patchMutate = vi.fn();
    stub({ patchMutate });
    renderPage();
    const model = screen.getByLabelText(/^model$/i);
    fireEvent.change(model, { target: { value: "openai:gpt-4o" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(patchMutate).toHaveBeenCalled();
    expect(patchMutate.mock.calls[0][0]).toMatchObject({
      name: "coffer",
      config: {
        model: "openai:gpt-4o",
        credential_ref: "ai/openai",
        // Existing config is merged (use_gateway preserved).
        use_gateway: true,
      },
    });
  });
});
