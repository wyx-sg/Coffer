// frontend/src/pages/sync/SyncPage.test.tsx
//
// Sync is a top-level page with three tabs — Runs, Setup and Machines — and it
// opens on Runs, because what a person opens Sync to find out is whether it is
// working.
//
// Status is gone: its two banners were a conflict and a held round, and neither
// is a state beside the history — each is the newest row OF it.
//
// The active tab is in the URL, so a link can land on Setup and a reload comes
// back where it was.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { acceptance } from "@/test/acceptance";

import { SyncPage } from "./SyncPage";

vi.mock("./SyncRunsTab", () => ({ SyncRunsTab: () => <div>runs tab</div> }));
vi.mock("./SyncSetupTab", () => ({ SyncSetupTab: () => <div>setup tab</div> }));
vi.mock("./SyncMachinesTab", () => ({ SyncMachinesTab: () => <div>machines tab</div> }));

let search = "";
function Probe() {
  search = useLocation().search;
  return null;
}

function renderAt(url = "/sync") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <SyncPage />
      <Probe />
    </MemoryRouter>,
  );
}

describe("SyncPage", () => {
  test("renders Runs, Setup and Machines, opening on Runs", () => {
    renderAt();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Runs", "Setup", "Machines"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("runs tab")).toBeInTheDocument();
  });

  test("carries its own page header rather than living under Settings", () => {
    renderAt();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/sync/i);
  });

  test("?tab= opens that tab, and switching tabs rewrites the URL", async () => {
    renderAt("/sync?tab=setup");
    expect(screen.getByRole("tab", { name: "Setup" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("setup tab")).toBeInTheDocument();

    // Radix activates a trigger on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Runs" }));
    // The landing tab needs no parameter, so the page's own URL is the shortest.
    await waitFor(() => expect(search).toBe(""));
    expect(screen.getByText("runs tab")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Setup" }));
    await waitFor(() => expect(search).toBe("?tab=setup"));

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Machines" }));
    await waitFor(() => expect(search).toBe("?tab=machines"));
    expect(screen.getByText("machines tab")).toBeInTheDocument();
  });

  test("a link to a tab that no longer exists lands on Runs rather than nowhere", () => {
    // `?tab=status` and `?tab=history` are in someone's history or a
    // bookmark. Neither may render an empty page.
    for (const stale of ["status", "history", "nope"]) {
      const view = renderAt(`/sync?tab=${stale}`);
      expect(screen.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByText("runs tab")).toBeInTheDocument();
      view.unmount();
    }
  });
  acceptance("vault-sync", "the Sync page opens on Runs beside Setup and Machines", () => {
    const view = renderAt();
    const tabs = screen.getAllByRole("tab");
    // Exactly three tabs — no Status tab beside them.
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Runs", "Setup", "Machines"]);
    expect(screen.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("runs tab")).toBeInTheDocument();
    view.unmount();

    // A link to the retired Status tab lands on Runs.
    renderAt("/sync?tab=status");
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("runs tab")).toBeInTheDocument();
  });
});
