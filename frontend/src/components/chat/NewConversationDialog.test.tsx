// components/chat/NewConversationDialog.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { NewConversationDialog } from "./NewConversationDialog";
import type { AgentInfo } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";

const agents: AgentInfo[] = [
  { agent_key: "builtin", display_name: "Coffer Assistant", available: true },
];

const models: Model[] = [
  {
    id: "m-1",
    display_name: "Sonnet",
    provider: "anthropic",
    model: "claude-sonnet-4-6",
    credential_ref: "ref",
    base_url: null,
    is_default: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

describe("NewConversationDialog", () => {
  test("renders nothing when closed", () => {
    render(
      <NewConversationDialog
        open={false}
        onOpenChange={vi.fn()}
        agents={agents}
        models={models}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.queryByText("New conversation")).not.toBeInTheDocument();
  });

  test("renders the dialog with an agent picker when open", () => {
    render(
      <NewConversationDialog
        open
        onOpenChange={vi.fn()}
        agents={agents}
        models={models}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText("New conversation")).toBeInTheDocument();
    expect(screen.getByText("Coffer Assistant")).toBeInTheDocument();
  });

  test("create submits the built-in agent with the default model in agent_config", () => {
    const onCreate = vi.fn();
    render(
      <NewConversationDialog
        open
        onOpenChange={vi.fn()}
        agents={agents}
        models={models}
        onCreate={onCreate}
      />,
    );
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /start conversation/i }));
    });
    expect(onCreate).toHaveBeenCalledWith({
      agent_key: "builtin",
      agent_config: { model_id: "m-1" },
    });
  });

  test("shows a hint when no models are configured", () => {
    render(
      <NewConversationDialog
        open
        onOpenChange={vi.fn()}
        agents={agents}
        models={[]}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText(/no models/i)).toBeInTheDocument();
  });

  test("seeds the default model even when models load after the dialog opened", () => {
    // agents and models are independent queries; opening the dialog before
    // models resolve must not lock the model selection to empty forever.
    const onCreate = vi.fn();
    const { rerender } = render(
      <NewConversationDialog
        open
        onOpenChange={vi.fn()}
        agents={agents}
        models={[]}
        onCreate={onCreate}
      />,
    );

    // Models arrive a moment later.
    rerender(
      <NewConversationDialog
        open
        onOpenChange={vi.fn()}
        agents={agents}
        models={models}
        onCreate={onCreate}
      />,
    );

    expect(screen.getByText("Sonnet")).toBeInTheDocument(); // default preselected
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /start conversation/i }));
    });
    expect(onCreate).toHaveBeenCalledWith({
      agent_key: "builtin",
      agent_config: { model_id: "m-1" },
    });
  });
});
