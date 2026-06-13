import type { PropsWithChildren } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { BuiltinAgentSection } from "./BuiltinAgentSection";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});
vi.mock("@/lib/hooks/useModels", () => ({
  useModels: () => ({
    data: [{ id: "1", display_name: "Qwen 2.5", provider: "ollama", model: "x", is_default: true }],
  }),
}));
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: () => ({ data: [{ name: "a" }, { name: "b" }, { name: "c" }] }),
}));

function wrap({ children }: PropsWithChildren) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

describe("BuiltinAgentSection", () => {
  test("shows the built-in agent, its model and skill count, separate from managed agents", () => {
    render(<BuiltinAgentSection builtin={{ display_name: "Coffer Assistant" }} />, { wrapper: wrap });
    expect(screen.getByText("Coffer Assistant")).toBeInTheDocument();
    expect(screen.getByText("Built-in")).toBeInTheDocument(); // the badge
    expect(screen.getByText(/runs on qwen 2\.5/i)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // skill count
  });

  test("Start chat goes to chat; Details opens the built-in detail page", () => {
    render(<BuiltinAgentSection builtin={{ display_name: "Coffer Assistant" }} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /start chat/i }));
    expect(navigate).toHaveBeenCalledWith("/chat");
    navigate.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /details/i }));
    expect(navigate).toHaveBeenCalledWith("/agents/builtin");
  });
});
