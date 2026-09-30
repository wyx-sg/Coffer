// src/components/shell/SidebarSettingsRow.test.tsx — the footer's Settings row on the collapsed icon rail (spec web-ui
// "Open Settings as a modal from the sidebar footer").
//
// Only the daemon's status probe is stubbed (unanswered); the footer, the
// tooltip and the Settings opener are real.
import { expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SidebarFooter } from "./SidebarFooter";

vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({ GET: () => new Promise(() => {}) }),
}));

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

acceptance("web-ui", "the collapsed rail keeps Settings as a gear with a tooltip", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/skills"]}>
        <TooltipProvider>
          <SidebarFooter collapsed />
        </TooltipProvider>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const gear = screen.getByTestId("sidebar-settings");
  // The gear alone: the word is gone from the rail, kept as its name.
  expect(gear).toHaveAccessibleName("Settings");
  expect(gear).not.toHaveTextContent("Settings");
  fireEvent.focus(gear);
  expect(await screen.findByRole("tooltip")).toHaveTextContent(/^Settings/);

  fireEvent.click(gear);
  expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
});
