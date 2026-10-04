// src/components/agent/AgentBadge.test.tsx — official marks on the neutral tile, the fallback glyph, labels and groups.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { AgentBadge } from "./AgentBadge";
import { AgentBadgeGroup } from "./AgentBadgeGroup";

function tileOf(el: HTMLElement): HTMLElement {
  const tile = el.querySelector<HTMLElement>("[data-agent-mark]");
  if (!tile) throw new Error("no tile");
  return tile;
}

describe("AgentBadge", () => {
  acceptance("web-ui", "a supported agent is shown by its official mark", () => {
    render(
      <>
        <AgentBadge type="claude_code" />
        <AgentBadge type="codex" state="not-connected" />
      </>,
    );
    const claude = screen.getByRole("img", { name: "Claude Code" });
    const codex = screen.getByRole("img", { name: "Codex, not connected to Coffer" });

    const claudeTile = tileOf(claude);
    const codexTile = tileOf(codex);
    expect(claudeTile).toHaveAttribute("data-agent-mark", "claude-spark");
    expect(codexTile).toHaveAttribute("data-agent-mark", "openai-blossom");
    expect(claudeTile.querySelector("img")?.getAttribute("src")).toMatch(/claude-spark-clay/);
    const blossoms = [...codexTile.querySelectorAll("img")].map((i) => i.getAttribute("src"));
    expect(blossoms.some((s) => /openai-blossom-black/.test(s ?? ""))).toBe(true);
    expect(blossoms.some((s) => /openai-blossom-white/.test(s ?? ""))).toBe(true);

    // The same neutral tile for both.
    expect(claudeTile).toHaveClass("bg-chip");
    expect(codexTile).toHaveClass("bg-chip");
    // No letters: a nameless badge renders no text at all.
    expect(claude.textContent).toBe("");
    expect(codex.textContent).toBe("");
  });

  acceptance("web-ui", "an agent Coffer does not support gets the neutral glyph", () => {
    render(<AgentBadge type="gemini_cli" name="Gemini CLI" />);
    const badge = screen.getByRole("img", { name: "Gemini CLI" });
    const tile = tileOf(badge);
    expect(tile).toHaveAttribute("data-agent-mark", "generic");
    expect(tile).toHaveClass("bg-chip");
    expect(tile.querySelector("svg")).not.toBeNull();
    expect(tile.querySelector("img")).toBeNull();
    expect(badge.textContent).toBe("");
  });

  test("the name shows beside the tile when asked", () => {
    render(<AgentBadge type="codex" showName size="lg" />);
    expect(screen.getByRole("img", { name: "Codex" })).toHaveTextContent("Codex");
  });

  test("not installed is a dashed empty tile", () => {
    render(<AgentBadge type="codex" state="not-installed" />);
    const missing = tileOf(screen.getByRole("img", { name: "Codex, not installed" }));
    expect(missing).toHaveClass("border-dashed", "bg-transparent");
  });
});

describe("AgentBadgeGroup", () => {
  test("orders Claude Code before Codex", () => {
    render(
      <AgentBadgeGroup
        agents={[
          { type: "codex", name: "Codex" },
          { type: "claude_code", name: "Claude Code" },
        ]}
        total={3}
      />,
    );
    const names = screen.getAllByRole("img").map((el) => el.getAttribute("aria-label"));
    expect(names).toEqual(["Claude Code", "Codex"]);
  });

  test("says All agents when every agent is chosen", () => {
    render(
      <AgentBadgeGroup
        agents={[
          { type: "claude_code", name: "Claude Code" },
          { type: "codex", name: "Codex" },
        ]}
        total={2}
      />,
    );
    expect(screen.getByText("All agents")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
