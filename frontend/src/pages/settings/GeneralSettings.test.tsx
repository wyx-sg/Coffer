// frontend/src/pages/settings/GeneralSettings.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { GeneralSettings } from "./GeneralSettings";
import { acceptance } from "@/test/acceptance";

// The daemon-residency card is General's second card and has its own tests
// (and its own daemon route); stub it so these stay about the preferences
// this page actually owns, and need no query client.
vi.mock("./DaemonResidencySettings", () => ({
  DaemonResidencySettings: () => null,
}));

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

const editorSelect = () => screen.getByRole("combobox", { name: /preferred editor/i });
// Radix Select opens on keyboard in jsdom (pointer events are stubbed).
const openEditorPicker = () => fireEvent.keyDown(editorSelect(), { key: "ArrowDown" });
const pickOption = (name: RegExp | string) => fireEvent.click(screen.getByRole("option", { name }));
const customInput = () =>
  screen.getByRole("textbox", { name: /custom editor command/i }) as HTMLInputElement;

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

  test("both controls are the same Select — no native <select> on the page", () => {
    render(<GeneralSettings />);
    expect(document.querySelectorAll("select")).toHaveLength(0);
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
  });
});

describe("GeneralSettings preferred editor", () => {
  test("picking a detected editor stores its launcher value", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    pickOption("Cursor");
    expect(localStorage.getItem(STORE_KEY)).toBe("cursor");
    expect(editorSelect()).toHaveTextContent("Cursor");
    // A detected editor needs no free-text field.
    expect(screen.queryByRole("textbox", { name: /custom editor command/i })).toBeNull();
  });

  test("choosing system default clears the override", () => {
    localStorage.setItem(STORE_KEY, "code");
    render(<GeneralSettings />);
    expect(editorSelect()).toHaveTextContent("Visual Studio Code");
    openEditorPicker();
    pickOption(/system default/i);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
    expect(editorSelect()).toHaveTextContent(/system default/i);
  });

  test("Custom… reveals a text field whose value persists on blur", () => {
    render(<GeneralSettings />);
    openEditorPicker();
    pickOption(/custom/i);
    const input = customInput();
    fireEvent.change(input, { target: { value: "/Applications/Zed.app" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBe("/Applications/Zed.app");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(localStorage.getItem(STORE_KEY)).toBeNull();
  });

  test("a stored custom value (not in the picker) shows as Custom with the field open", () => {
    localStorage.setItem(STORE_KEY, "/opt/weird/editor");
    render(<GeneralSettings />);
    expect(editorSelect()).toHaveTextContent(/custom/i);
    expect(customInput().value).toBe("/opt/weird/editor");
  });
});

acceptance("web-ui", "general tab persists the preferred editor", () => {
  const { unmount } = render(<GeneralSettings />);

  // Choosing an application from the picker persists it.
  openEditorPicker();
  pickOption("Visual Studio Code");
  expect(localStorage.getItem("coffer.preferredEditor")).toBe("code");

  // Reloading the page shows the same persisted value in the picker.
  unmount();
  render(<GeneralSettings />);
  expect(editorSelect()).toHaveTextContent("Visual Studio Code");

  // Clearing the override restores the operating-system default (empty store).
  openEditorPicker();
  pickOption(/system default/i);
  expect(localStorage.getItem("coffer.preferredEditor")).toBeNull();
});
