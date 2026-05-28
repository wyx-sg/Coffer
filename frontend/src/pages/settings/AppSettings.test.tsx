// frontend/src/pages/settings/AppSettings.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppSettings } from "./AppSettings";

// AppSettings is Tauri-only — mock the Tauri layer so the desktop-app
// branch (the launch-at-login control) renders under jsdom.
vi.mock("@/lib/tauri", () => ({
  isTauri: () => true,
  getAutostartEnabled: vi.fn().mockResolvedValue(false),
  setAutostartEnabled: vi.fn(),
}));

describe("AppSettings", () => {
  test("renders the launch-at-login control inside the desktop app", () => {
    render(<AppSettings />);
    expect(screen.getByText("Launch at Login")).toBeInTheDocument();
    expect(screen.getByText(/Start Coffer automatically/i)).toBeInTheDocument();
  });
});
