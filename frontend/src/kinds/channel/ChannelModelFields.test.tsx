// frontend/src/kinds/channel/ChannelModelFields.test.tsx
//
// The channel's model curation (spec channels FR-071) pinned to its four rules:
// ticking nothing means NO RESTRICTION (never "no models"), the default is
// picked out of the range once there is one, narrowing the range past the
// pinned model unpins it rather than submitting a pair the backend refuses, and
// re-binding the agent drops ids that belonged to the old one.
import { useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ChannelModelFields } from "./ChannelModelFields";

vi.mock("@/lib/api/agentModels", () => ({ agentModelsApi: { list: vi.fn() } }));

const { agentModelsApi } = await import("@/lib/api/agentModels");
const listMock = vi.mocked(agentModelsApi.list);

const CLAUDE = [
  { id: "claude-opus-5", label: "Opus 5", description: "" },
  { id: "claude-fable-5-1", label: "", description: "" },
  { id: "claude-haiku-4-5", label: "Haiku 4.5", description: "" },
];
const CODEX = [{ id: "gpt-5-codex", label: "", description: "" }];

/** A controlled host, so a tick is observed exactly as a dialog would see it. */
function Harness({ agentKey = "claude_code" }: { agentKey?: string }) {
  const [defaultModel, setDefaultModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ChannelModelFields
        agentKey={agentKey}
        defaultModel={defaultModel}
        models={models}
        onDefaultModelChange={setDefaultModel}
        onModelsChange={setModels}
        idPrefix="t"
      />
    </QueryClientProvider>
  );
}

const box = (id: string) => screen.getByRole("checkbox", { name: id }) as HTMLInputElement;

function openDefaultOptions(): string[] {
  const trigger = screen.getByRole("combobox", { name: /default model|默认模型/i });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  listMock.mockImplementation(async (agentKey: string) => ({
    models: agentKey === "codex" ? CODEX : CLAUDE,
  }));
});

describe("ChannelModelFields", () => {
  test("an uncurated channel shows the whole catalogue and says it is unrestricted", async () => {
    render(<Harness />);

    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(3));
    for (const m of CLAUDE) expect(box(m.id).checked).toBe(false);
    // Nothing ticked must READ as "everything", never as "nothing".
    expect(screen.getByText(/no restriction|未限制/i)).toBeInTheDocument();
  });

  test("the default model offers an explicit 'not pinned' choice over the catalogue", async () => {
    render(<Harness />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(3));

    const options = openDefaultOptions();
    expect(options[0]).toMatch(/not pinned|不指定/i);
    expect(options).toContain("claude-opus-5");
    expect(options).toContain("claude-haiku-4-5");
  });

  test("a curated range is what the default is picked out of", async () => {
    render(<Harness />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(3));

    fireEvent.click(box("claude-opus-5"));
    expect(screen.getByText(/1 of 3|3 个模型中的 1 个/i)).toBeInTheDocument();

    const options = openDefaultOptions();
    expect(options).toContain("claude-opus-5");
    // Out of range ⇒ never offered as the default, so the pair the backend
    // refuses cannot be assembled by pointing and clicking.
    expect(options).not.toContain("claude-haiku-4-5");
  });

  test("un-ticking the pinned model unpins it instead of leaving it out of range", async () => {
    render(<Harness />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(3));

    fireEvent.click(box("claude-opus-5"));
    fireEvent.click(box("claude-haiku-4-5"));
    openDefaultOptions();
    fireEvent.click(screen.getByRole("option", { name: "claude-opus-5" }));
    expect(screen.getByRole("combobox", { name: /default model|默认模型/i })).toHaveTextContent(
      "claude-opus-5",
    );

    fireEvent.click(box("claude-opus-5"));

    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /default model|默认模型/i })).toHaveTextContent(
        /not pinned|不指定/i,
      ),
    );
  });

  test("emptying the range restores 'no restriction' and keeps the pinned model", async () => {
    render(<Harness />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(3));

    fireEvent.click(box("claude-opus-5"));
    openDefaultOptions();
    fireEvent.click(screen.getByRole("option", { name: "claude-opus-5" }));
    fireEvent.click(box("claude-opus-5"));

    // Back to the out-of-the-box state: [] is "not curated", not "offer
    // nothing" — and with no range the pin is not out of anything, so it stays.
    expect(screen.getByText(/no restriction|未限制/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /default model|默认模型/i })).toHaveTextContent(
      "claude-opus-5",
    );
  });

  test("re-binding the agent drops ids that belonged to the old one", async () => {
    const { rerender } = render(<Harness agentKey="claude_code" />);
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(3));
    fireEvent.click(box("claude-opus-5"));
    openDefaultOptions();
    fireEvent.click(screen.getByRole("option", { name: "claude-opus-5" }));

    rerender(<Harness agentKey="codex" />);

    // A Claude id on a Codex channel would be submitted verbatim and fail the
    // turn, so the binding change clears both fields.
    await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(1));
    expect(box("gpt-5-codex").checked).toBe(false);
    expect(screen.getByText(/no restriction|未限制/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /default model|默认模型/i })).toHaveTextContent(
      /not pinned|不指定/i,
    );
  });

  test("an agent whose CLI reports nothing says so instead of an empty tick list", async () => {
    listMock.mockResolvedValue({ models: [] });
    render(<Harness />);

    expect(await screen.findByText(/no model catalogue|暂无可用的模型清单/i)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
