import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { DraftThread } from "./DraftThread";
import type { AgentInfo } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";

const agents: AgentInfo[] = [
  { agent_key: "builtin", display_name: "Coffer Assistant", available: true },
];
const models: Model[] = [
  {
    id: "m1",
    display_name: "Test Model",
    provider: "anthropic",
    model: "x",
    is_default: true,
    created_at: "x",
    updated_at: "x",
  },
];

function renderDraft(overrides: Partial<React.ComponentProps<typeof DraftThread>> = {}) {
  const onSend = vi.fn();
  render(
    <MemoryRouter>
      <DraftThread
        agents={agents}
        models={models}
        agentKey="builtin"
        modelId="m1"
        onAgentChange={vi.fn()}
        onModelChange={vi.fn()}
        onSend={onSend}
        {...overrides}
      />
    </MemoryRouter>,
  );
  return { onSend };
}

describe("DraftThread", () => {
  test("shows the start guide and a composer when a model exists", () => {
    renderDraft();
    expect(screen.getByText(/start a new conversation/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  test("sends the typed first message through onSend", () => {
    const { onSend } = renderDraft();
    const box = screen.getByRole("textbox", { name: /message input/i });
    fireEvent.change(box, { target: { value: "first message" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("first message");
  });

  test("shows the no-model empty state instead of a composer when no models", () => {
    renderDraft({ models: [] });
    expect(screen.getByText("No model configured")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
  });
});
