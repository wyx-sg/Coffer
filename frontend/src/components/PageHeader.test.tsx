// src/components/PageHeader.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Library } from "lucide-react";

import { PageHeader } from "./PageHeader";

function renderHeader(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("PageHeader", () => {
  test("renders the title as the page's h1 with an optional subtitle", () => {
    renderHeader(<PageHeader icon={Library} title="Knowledge" subtitle="What agents read" />);
    expect(screen.getByRole("heading", { level: 1, name: "Knowledge" })).toBeInTheDocument();
    expect(screen.getByText("What agents read")).toBeInTheDocument();
  });

  test("renders the back link, badges and actions slots when given", () => {
    renderHeader(
      <PageHeader
        icon={Library}
        title="alpha"
        back={{ to: "/knowledge", label: "Knowledge" }}
        badges={<span data-testid="badge">enabled</span>}
        actions={<button type="button">Edit</button>}
      />,
    );
    expect(screen.getByRole("link", { name: "Knowledge" })).toHaveAttribute("href", "/knowledge");
    expect(screen.getByTestId("badge")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  test("renders no back link when the prop is omitted", () => {
    renderHeader(<PageHeader icon={Library} title="Knowledge" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
