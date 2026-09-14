// frontend/src/pages/sync/SyncPage.test.tsx
//
// Sync is a top-level page with exactly two tabs. Conflicts and held rounds
// are banners on Status, never a third tab: they are states the vault passes
// through, and a permanent tab would read as a place you are meant to visit.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SyncPage } from "./SyncPage";

vi.mock("./SyncStatusTab", () => ({ SyncStatusTab: () => <div>status tab</div> }));
vi.mock("./SyncMachinesTab", () => ({ SyncMachinesTab: () => <div>machines tab</div> }));

describe("SyncPage", () => {
  test("renders exactly two tabs, opening on Status", () => {
    render(<SyncPage />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("status tab")).toBeInTheDocument();
  });

  test("carries its own page header rather than living under Settings", () => {
    render(<SyncPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/sync/i);
  });
});
