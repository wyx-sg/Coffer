// frontend/src/pages/sync/SyncPage.test.tsx
//
// Sync is a top-level page with three tabs — Status, History, Machines.
// Conflicts and held rounds are banners on Status, never a tab of their own:
// they are states the vault passes through, and a permanent tab would read as
// a place you are meant to visit. History is different: it is a record, and a
// record is exactly the kind of thing you go and look at — so the active tab
// is in the URL, and a link can land on it.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { SyncPage } from "./SyncPage";

vi.mock("./SyncStatusTab", () => ({ SyncStatusTab: () => <div>status tab</div> }));
vi.mock("./SyncHistoryTab", () => ({ SyncHistoryTab: () => <div>history tab</div> }));
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
  test("renders Status, History and Machines, opening on Status", () => {
    renderAt();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Status", "History", "Machines"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("status tab")).toBeInTheDocument();
  });

  test("carries its own page header rather than living under Settings", () => {
    renderAt();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/sync/i);
  });

  test("?tab= opens that tab, and switching tabs rewrites the URL", async () => {
    renderAt("/sync?tab=machines");
    expect(screen.getByRole("tab", { name: "Machines" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("machines tab")).toBeInTheDocument();

    // Radix activates a trigger on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "History" }));
    await waitFor(() => expect(search).toBe("?tab=history"));
    expect(screen.getByText("history tab")).toBeInTheDocument();

    // The default tab needs no parameter.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Status" }));
    await waitFor(() => expect(search).toBe(""));
  });

  test("an unknown ?tab= falls back to Status", () => {
    renderAt("/sync?tab=nope");
    expect(screen.getByRole("tab", { name: "Status" })).toHaveAttribute("aria-selected", "true");
  });
});
