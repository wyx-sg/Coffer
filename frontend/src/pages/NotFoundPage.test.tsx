// frontend/src/pages/NotFoundPage.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { NotFoundPage } from "./NotFoundPage";

describe("NotFoundPage", () => {
  test("renders heading and echoes the unknown path", () => {
    render(
      <MemoryRouter initialEntries={["/bogus"]}>
        <Routes>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );

    // The page title comes from i18n; falls back to the key when keys
    // aren't resolved (vitest setup doesn't always wire i18n) — accept
    // either, but require at least the path echo to ensure useLocation
    // wiring works.
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    // The current path is interpolated into the subtitle copy.
    expect(screen.getByText(/\/bogus/)).toBeInTheDocument();
    // The "back to resources" CTA must be a link to /mcp-servers.
    const back = screen.getByRole("link");
    expect(back).toHaveAttribute("href", "/mcp-servers");
  });
});
