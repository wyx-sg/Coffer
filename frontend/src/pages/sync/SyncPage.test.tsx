// frontend/src/pages/sync/SyncPage.test.tsx
//
// Sync is a top-level page with three tabs — Status, History, Machines.
// Conflicts and held rounds are banners on Status, never a tab of their own:
// they are states the vault passes through, and a permanent tab would read as
// a place you are meant to visit. History is different: it is a record, and a
// record is exactly the kind of thing you go and look at.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SyncPage } from "./SyncPage";

vi.mock("./SyncStatusTab", () => ({ SyncStatusTab: () => <div>status tab</div> }));
vi.mock("./SyncHistoryTab", () => ({ SyncHistoryTab: () => <div>history tab</div> }));
vi.mock("./SyncMachinesTab", () => ({ SyncMachinesTab: () => <div>machines tab</div> }));

describe("SyncPage", () => {
  test("renders Status, History and Machines, opening on Status", () => {
    render(<SyncPage />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Status", "History", "Machines"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("status tab")).toBeInTheDocument();
  });

  test("carries its own page header rather than living under Settings", () => {
    render(<SyncPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/sync/i);
  });
});
