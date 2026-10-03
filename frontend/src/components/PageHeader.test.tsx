// src/components/PageHeader.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { PageHeader } from "./PageHeader";

function renderHeader(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("PageHeader", () => {
  test("renders the title as the page's h1 with an optional subtitle", () => {
    renderHeader(<PageHeader title="Knowledge" subtitle="What agents read" />);
    expect(screen.getByRole("heading", { level: 1, name: "Knowledge" })).toBeInTheDocument();
    expect(screen.getByText("What agents read")).toBeInTheDocument();
  });

  test("renders the badges and actions slots when given", () => {
    renderHeader(
      <PageHeader
        title="alpha"
        badges={<span data-testid="badge">enabled</span>}
        actions={<button type="button">Edit</button>}
      />,
    );
    expect(screen.getByTestId("badge")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  test("experimental puts the tag beside the title, outside the heading's name", () => {
    renderHeader(<PageHeader title="Usage" experimental />);
    expect(screen.getByRole("heading", { level: 1, name: "Usage" })).toBeInTheDocument();
    expect(screen.getByText("Experimental")).toBeInTheDocument();
  });

  test("no tag unless asked", () => {
    renderHeader(<PageHeader title="Usage" />);
    expect(screen.queryByText("Experimental")).toBeNull();
  });
});
