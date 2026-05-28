// frontend/src/lib/components/ResourceListView.test.tsx
import { beforeEach, describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { _resetKindRegistry, registerKindUI } from "./kindRegistry";
import { ResourceListView } from "./ResourceListView";
import type { components } from "@/lib/api/types";

type ResourceOut = components["schemas"]["ResourceOut"];

function fakeResource(overrides: Partial<ResourceOut> = {}): ResourceOut {
  return {
    ref: "fake_kind:t",
    kind: "fake_kind",
    name: "t",
    description: null,
    config: {},
    enabled: true,
    created_at: "2026-05-21T00:00:00Z",
    updated_at: "2026-05-21T00:00:00Z",
    ...overrides,
  };
}

describe("ResourceListView", () => {
  beforeEach(() => {
    _resetKindRegistry();
  });

  test("renders empty message when list is empty", () => {
    render(<ResourceListView resources={[]} emptyMessage="Nothing yet" />);
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
  });

  test("renders kind-specific card for registered kinds", () => {
    registerKindUI({
      name: "fake_kind",
      displayName: "Fake",
      Card: ({ resource }) => <div data-testid="fake-card">{resource.name}</div>,
    });
    render(<ResourceListView resources={[fakeResource()]} />);
    expect(screen.getByTestId("fake-card")).toHaveTextContent("t");
  });

  test("falls back to unknown-kind card when no registration", () => {
    render(<ResourceListView resources={[fakeResource({ kind: "ghost" })]} />);
    expect(screen.getByText(/unregistered kind: ghost/)).toBeInTheDocument();
  });
});
