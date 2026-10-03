// src/lib/hooks/useAttentionSignals.test.tsx — which sidebar entries carry a count badge, and the badge itself.
//
// The sidebar speaks only through counts of things that need the user
// (design note n_shell); informational items and the Knowledge inbox never
// become badges (design decision 15).
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { AttentionDot } from "@/components/shell/AttentionDot";
import { countByEntry } from "./useAttentionSignals";
import type { AttentionItem } from "./useAttention";

function item(kind: string, severity: string): AttentionItem {
  return { kind, severity } as unknown as AttentionItem;
}

describe("countByEntry", () => {
  test("counts what needs the user per entry", () => {
    const signals = countByEntry([
      item("mcp_server", "warning"),
      item("mcp_server", "error"),
      item("channel", "warning"),
      item("channel", "warning"),
    ]);
    expect(signals["/mcp-servers"]).toEqual({ count: 2 });
    expect(signals["/channels"]).toEqual({ count: 2 });
  });

  test("an informational item never becomes a badge", () => {
    expect(countByEntry([item("agent", "info")])).toEqual({});
  });

  test("the Knowledge inbox and Memory never badge their entries", () => {
    const signals = countByEntry([
      item("knowledge", "warning"),
      item("knowledge_collection", "warning"),
      item("memory", "warning"),
    ]);
    expect(signals["/knowledge"]).toBeUndefined();
    expect(signals["/memory"]).toBeUndefined();
  });
});

describe("AttentionDot", () => {
  test("expanded it shows the count in the danger-strong tone, capped at 9+", () => {
    const { unmount } = render(<AttentionDot entry="/mcp-servers" collapsed={false} count={3} />);
    const badge = screen.getByTestId("nav-dot-mcp-servers");
    expect(badge).toHaveTextContent("3");
    expect(badge).toHaveClass("bg-danger-strong");
    expect(badge).toHaveAccessibleName("Needs your attention");
    unmount();

    render(<AttentionDot entry="/mcp-servers" collapsed={false} count={12} />);
    expect(screen.getByTestId("nav-dot-mcp-servers")).toHaveTextContent("9+");
  });

  test("on the rail it is a dot of the same colour with the same name", () => {
    render(<AttentionDot entry="/mcp-servers" collapsed count={3} />);
    const dot = screen.getByTestId("nav-dot-mcp-servers");
    expect(dot).toHaveTextContent("");
    expect(dot).toHaveClass("bg-danger-strong");
    expect(dot).toHaveAccessibleName("Needs your attention");
  });
});
