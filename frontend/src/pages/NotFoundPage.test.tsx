// frontend/src/pages/NotFoundPage.test.tsx — the 404 (board 1.2.16): the address, the closest page, Overview and ⌘K.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { closestPage } from "@/lib/navigation";
import { acceptance } from "@/test/acceptance";
import { NotFoundPage } from "./NotFoundPage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("NotFoundPage", () => {
  acceptance("web-ui", "an unknown address suggests the closest page", () => {
    renderAt("/mcp/sentri");
    expect(
      screen.getByRole("heading", { level: 1, name: "Nothing lives at this address" }),
    ).toBeInTheDocument();
    expect(screen.getByText("/mcp/sentri")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Did you mean/ })).toHaveAttribute(
      "href",
      "/mcp-servers",
    );
    expect(screen.getByRole("link", { name: "Back to Overview" })).toHaveAttribute("href", "/");
    // Search Coffer asks the shell (Layout) for the command palette.
    const heard = vi.fn();
    window.addEventListener("coffer:open-palette", heard);
    fireEvent.click(screen.getByRole("button", { name: /Search Coffer/ }));
    expect(heard).toHaveBeenCalledOnce();
    window.removeEventListener("coffer:open-palette", heard);
  });
});

describe("closestPage", () => {
  test("a prefix or a near miss of a page's address suggests it; nothing close suggests nothing", () => {
    expect(closestPage("/mcp/sentri")).toBe("/mcp-servers");
    expect(closestPage("/skils")).toBe("/skills");
    expect(closestPage("/zzzzzzzz")).toBeNull();
    expect(closestPage("/")).toBeNull();
  });
});
