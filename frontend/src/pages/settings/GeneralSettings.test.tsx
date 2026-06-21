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

const editorInput = () =>
  screen.getByRole("textbox", { name: /preferred editor/i }) as HTMLInputElement;
const openEditorPicker = () =>
  fireEvent.click(screen.getByRole("button", { name: /choose editor/i }));

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
  test("picking a detected editor fills the field with its launcher value", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    fireEvent.click(screen.getByRole("button", { name: "Cursor" }));
    expect(localStorage.getItem(STORE_KEY)).toBe("cursor");
    // The value lands in the editable field in place — no separate text box.
    expect(editorInput().value).toBe("cursor");
  });

  test("choosing system default clears the override", () => {
    localStorage.setItem(STORE_KEY, "code");
    render(<GeneralSettings />);
    expect(editorInput().value).toBe("code");
    openEditorPicker();
    fireEvent.click(screen.getByRole("button", { name: /system default/i }));
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
    expect(editorInput().value).toBe("");
  });

  test("a custom editor is typed straight into the field and persists", () => {
    render(<GeneralSettings />);
    const input = editorInput();
    fireEvent.change(input, { target: { value: "/Applications/Zed.app" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBe("/Applications/Zed.app");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
  });

  test("a stored custom value (not in the picker) shows in the field on load", () => {
    localStorage.setItem(STORE_KEY, "/opt/weird/editor");
    render(<GeneralSettings />);
    expect(editorInput().value).toBe("/opt/weird/editor");
  });
});

acceptance("002-ui-shell", "general tab persists the preferred editor", () => {
  const { unmount } = render(<GeneralSettings />);

  // Choosing an application from the picker persists it.
  fireEvent.click(screen.getByRole("button", { name: /choose editor/i }));
  fireEvent.click(screen.getByRole("button", { name: "Visual Studio Code" }));
  expect(localStorage.getItem("coffer.preferredEditor")).toBe("code");

  // Reloading the page shows the same persisted value in the field.
  unmount();
  render(<GeneralSettings />);
  expect(editorInput().value).toBe("code");

  // Clearing the override restores the operating-system default (empty store).
  fireEvent.click(screen.getByRole("button", { name: /choose editor/i }));
  fireEvent.click(screen.getByRole("button", { name: /system default/i }));
  expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
});
