// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { GeneralSettings } from "./GeneralSettings";
import { acceptance } from "@/test/acceptance";

// The picker lists editors the daemon detected as installed; stub that out so
// these tests drive a fixed set without a live daemon.
vi.mock("@/lib/hooks/useEditors", () => ({
  useDetectedEditors: () => ({
    data: [
      { label: "Visual Studio Code", value: "code" },
      { label: "Cursor", value: "cursor" },
    ],
  }),
}));

afterEach(() => localStorage.clear());

const STORE_KEY = "coffer.preferredEditor";

function openEditorPicker() {
  fireEvent.click(screen.getByRole("combobox", { name: /preferred editor/i }));
}

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
  test("picking a detected editor stores its launcher value", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    fireEvent.click(screen.getByRole("option", { name: "Cursor" }));
    expect(localStorage.getItem(STORE_KEY)).toBe("cursor");
    // The trigger now reflects the chosen editor.
    expect(screen.getByRole("combobox", { name: /preferred editor/i })).toHaveTextContent("Cursor");
  });

  test("choosing system default clears the override", () => {
    localStorage.setItem(STORE_KEY, "code");
    render(<GeneralSettings />);
    openEditorPicker();
    fireEvent.click(screen.getByRole("option", { name: /system default/i }));
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
  });

  test("custom entry reveals a text field, persists it, and clears when emptied", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    fireEvent.click(screen.getByRole("option", { name: /custom/i }));

    const input = screen.getByLabelText(/custom/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "/Applications/Zed.app" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBe("/Applications/Zed.app");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
  });

  test("a stored custom value (not in the picker) shows the custom field on load", () => {
    localStorage.setItem(STORE_KEY, "/opt/weird/editor");
    render(<GeneralSettings />);
    const input = screen.getByLabelText(/custom/i) as HTMLInputElement;
    expect(input.value).toBe("/opt/weird/editor");
  });
});

acceptance("002-ui-shell", "general tab persists the preferred editor", () => {
  const { unmount } = render(<GeneralSettings />);

  // Choosing an application from the picker persists it.
  fireEvent.click(screen.getByRole("combobox", { name: /preferred editor/i }));
  fireEvent.click(screen.getByRole("option", { name: "Visual Studio Code" }));
  expect(localStorage.getItem("coffer.preferredEditor")).toBe("code");

  // Reloading the page shows the same persisted value.
  unmount();
  render(<GeneralSettings />);
  expect(screen.getByRole("combobox", { name: /preferred editor/i })).toHaveTextContent(
    "Visual Studio Code",
  );

  // Clearing the override restores the operating-system default (empty store).
  fireEvent.click(screen.getByRole("combobox", { name: /preferred editor/i }));
  fireEvent.click(screen.getByRole("option", { name: /system default/i }));
  expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
});
