// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { GeneralSettings } from "./GeneralSettings";
import { acceptance } from "@/test/acceptance";

afterEach(() => localStorage.clear());

describe("GeneralSettings", () => {
  test("renders the default page-size control reflecting the stored preference", () => {
    localStorage.setItem("coffer.pageSize", "50");
    render(<GeneralSettings />);
    expect(screen.getByText(/default rows per page/i)).toBeInTheDocument();
    // The Select trigger shows the persisted value.
    expect(screen.getByRole("combobox", { name: /default rows per page/i })).toHaveTextContent(
      "50",
    );
  });
});

describe("GeneralSettings preferred editor", () => {
  test("persists a typed editor and clears the override when emptied", () => {
    render(<GeneralSettings />);
    const input = screen.getByLabelText(/preferred editor/i) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "cursor" } });
    fireEvent.blur(input);
    expect(localStorage.getItem("coffer.preferredEditor")).toBe("cursor");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
  });
});

acceptance("002-ui-shell", "general tab persists the preferred editor", () => {
  const { unmount } = render(<GeneralSettings />);
  const input = screen.getByLabelText(/preferred editor/i) as HTMLInputElement;
  fireEvent.change(input, { target: { value: "/Applications/Zed.app" } });
  fireEvent.blur(input);
  expect(localStorage.getItem("coffer.preferredEditor")).toBe("/Applications/Zed.app");

  // Reloading the page shows the same persisted value.
  unmount();
  render(<GeneralSettings />);
  const reloaded = screen.getByLabelText(/preferred editor/i) as HTMLInputElement;
  expect(reloaded.value).toBe("/Applications/Zed.app");

  // Clearing the override restores the operating-system default (empty store).
  fireEvent.change(reloaded, { target: { value: "" } });
  fireEvent.blur(reloaded);
  expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
});
