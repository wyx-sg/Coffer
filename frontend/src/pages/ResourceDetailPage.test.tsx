// frontend/src/pages/ResourceDetailPage.test.tsx
//
// Tests the kind-dispatch shim: ResourceDetailPage looks up the kind in
// the kindRegistry and either renders the kind-specific DetailPage,
// redirects to /resources when the kind has no detail page, or shows an
// "unknown kind" card when the kind isn't registered.

import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ResourceDetailPage } from "./ResourceDetailPage";
import { _resetKindRegistry, registerKindUI } from "@/lib/components/kindRegistry";

function FakeCard() {
  return <div data-testid="fake-card">card</div>;
}

function FakeDetail({ name }: { name: string }) {
  return <div data-testid="fake-detail">detail: {name}</div>;
}

function wrap(route: string) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/resources/:kind/:name" element={<ResourceDetailPage />} />
        <Route path="/resources" element={<div data-testid="resources-page">resources</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResourceDetailPage", () => {
  beforeEach(() => {
    _resetKindRegistry();
  });
  afterEach(() => {
    _resetKindRegistry();
  });

  test("renders the kind-specific DetailPage for a registered kind", () => {
    registerKindUI({
      name: "fake_kind",
      displayName: "Fake",
      Card: FakeCard,
      DetailPage: FakeDetail,
    });
    render(wrap("/resources/fake_kind/foo"));
    expect(screen.getByTestId("fake-detail")).toHaveTextContent("detail: foo");
  });

  test("redirects to /resources when the kind has no DetailPage", () => {
    registerKindUI({
      name: "no_detail",
      displayName: "NoDetail",
      Card: FakeCard,
    });
    render(wrap("/resources/no_detail/bar"));
    expect(screen.getByTestId("resources-page")).toBeInTheDocument();
  });

  test("shows the unknown-kind card when the kind isn't registered", () => {
    render(wrap("/resources/totally_unknown/baz"));
    // Either the translated copy or the raw key — accept the heading
    // role to keep the test resilient to i18n wiring.
    expect(screen.getByText(/totally_unknown/)).toBeInTheDocument();
  });
});
