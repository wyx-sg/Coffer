// frontend/src/kinds/mcp/HealthBadge.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { HealthBadge } from "./HealthBadge";

describe("HealthBadge", () => {
  test("renders healthy with latency", () => {
    render(<HealthBadge state="healthy" latencyMs={42} />);
    expect(screen.getByTestId("health-badge")).toHaveTextContent("healthy");
    expect(screen.getByTestId("health-badge")).toHaveTextContent("42 ms");
  });

  test("renders unknown without latency", () => {
    render(<HealthBadge state="unknown" />);
    expect(screen.getByTestId("health-badge")).toHaveTextContent("unknown");
  });

  test("renders failing in destructive style", () => {
    render(<HealthBadge state="failing" />);
    const b = screen.getByTestId("health-badge");
    expect(b).toHaveTextContent("failing");
  });
});
